mod keychain;
mod provider_config;
mod security;
mod sidecar;

use provider_config::{ProviderConfiguration, ProviderConfigurationView};
use sidecar::{SidecarConnectionView, SidecarDiagnosticsView, SidecarSupervisor};
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder},
    AppHandle, Emitter, Manager, State, WebviewWindowBuilder,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ApplicationEventAction {
    None,
    ReopenMainWindow,
    ShutdownSidecar,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum MainWindowReopenAction {
    ShowExisting,
    BuildFromConfig,
    None,
}

fn application_event_action(event: &tauri::RunEvent) -> ApplicationEventAction {
    match event {
        #[cfg(target_os = "macos")]
        tauri::RunEvent::Reopen { .. } => ApplicationEventAction::ReopenMainWindow,
        tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
            ApplicationEventAction::ShutdownSidecar
        }
        _ => ApplicationEventAction::None,
    }
}

fn main_window_reopen_action(window_exists: bool, config_exists: bool) -> MainWindowReopenAction {
    if window_exists {
        MainWindowReopenAction::ShowExisting
    } else if config_exists {
        MainWindowReopenAction::BuildFromConfig
    } else {
        MainWindowReopenAction::None
    }
}

fn should_hide_main_window(label: &str, event: &tauri::WindowEvent) -> bool {
    label == "main" && matches!(event, tauri::WindowEvent::CloseRequested { .. })
}

#[tauri::command]
fn get_sidecar_connection(state: State<'_, SidecarSupervisor>) -> SidecarConnectionView {
    state.connection_view()
}

#[tauri::command]
fn get_sidecar_diagnostics(state: State<'_, SidecarSupervisor>) -> SidecarDiagnosticsView {
    state.diagnostics_view()
}

#[tauri::command]
fn get_provider_configuration(app: AppHandle) -> Result<ProviderConfigurationView, String> {
    let path = provider_config::config_path(
        &app.path()
            .app_data_dir()
            .map_err(|_| "Keen could not locate its private app data.".to_owned())?,
    );
    let configuration = provider_config::load(&path)?;
    Ok(match configuration {
        Some(value) => {
            let api_key_configured = provider_config::remote_key_origin(&value)?
                .map(|origin| keychain::has(&origin))
                .transpose()?
                .unwrap_or(false);
            ProviderConfigurationView {
                configured: true,
                provider: Some(value.provider),
                endpoint: Some(value.endpoint),
                model: Some(value.model),
                api_key_configured,
            }
        }
        None => ProviderConfigurationView {
            configured: false,
            provider: None,
            endpoint: None,
            model: None,
            api_key_configured: false,
        },
    })
}

#[tauri::command]
async fn save_provider_configuration(
    app: AppHandle,
    state: State<'_, SidecarSupervisor>,
    configuration: ProviderConfiguration,
    api_key: Option<String>,
) -> Result<SidecarConnectionView, String> {
    let configuration = provider_config::canonicalize(configuration)?;
    let path = provider_config::config_path(
        &app.path()
            .app_data_dir()
            .map_err(|_| "Keen could not locate its private app data.".to_owned())?,
    );
    let key_origin = provider_config::remote_key_origin(&configuration)?;
    if let Some(origin) = key_origin.as_deref() {
        if api_key.is_none() && !keychain::has(origin)? {
            return Err(
                "An API key is required for this remote OpenAI-compatible endpoint.".to_owned(),
            );
        }
        if let Some(value) = api_key.as_deref() {
            keychain::save(origin, value)?;
        }
    }
    if let Err(error) = provider_config::save(&path, &configuration) {
        let key_note = if key_origin.is_some() && api_key.is_some() {
            " The provider settings were not switched, but the API key may have been saved in macOS Keychain for this endpoint."
        } else {
            " The provider settings were not switched."
        };
        return Err(format!("{error}{key_note}"));
    }
    let supervisor = state.inner().clone();
    let restart_app = app.clone();
    match tauri::async_runtime::spawn_blocking(move || supervisor.restart_for_configuration(restart_app)).await {
        Ok(Ok(view)) => Ok(view),
        Ok(Err(_)) | Err(_) => Err("Provider settings were saved, but Keen could not begin restarting the local learning service. The service may still be using its previous runtime configuration; retry from Settings after it recovers.".to_owned()),
    }
}

#[tauri::command]
async fn restart_sidecar(
    app: AppHandle,
    state: State<'_, SidecarSupervisor>,
    reason: Option<String>,
) -> Result<SidecarConnectionView, String> {
    let supervisor = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || supervisor.restart(app, reason))
        .await
        .map_err(|error| format!("learning-core restart task failed: {error}"))?
}

fn reopen_main_window(app: &AppHandle) -> tauri::Result<()> {
    let window = app.get_webview_window("main");
    let config = app
        .config()
        .app
        .windows
        .iter()
        .find(|config| config.label == "main");
    match main_window_reopen_action(window.is_some(), config.is_some()) {
        MainWindowReopenAction::ShowExisting => {
            if let Some(window) = window {
                window.show()?;
                window.set_focus()?;
            }
        }
        MainWindowReopenAction::BuildFromConfig => {
            if let Some(config) = config {
                WebviewWindowBuilder::from_config(app, config)?.build()?;
            }
        }
        MainWindowReopenAction::None => {}
    }
    Ok(())
}

fn install_native_menu(app: &tauri::App) -> tauri::Result<()> {
    let settings = MenuItemBuilder::with_id("open-settings", "Settings…")
        .accelerator("CmdOrCtrl+,")
        .build(app)?;
    let application_name = app.config().product_name.as_deref().unwrap_or("Keen");
    let application_menu = SubmenuBuilder::new(app, application_name)
        .about(None)
        .separator()
        .item(&settings)
        .separator()
        .services()
        .separator()
        .hide()
        .hide_others()
        .show_all()
        .separator()
        .quit()
        .build()?;

    let new_conversation = MenuItemBuilder::with_id("new-conversation", "New Learning")
        .accelerator("CmdOrCtrl+N")
        .build(app)?;
    let import_source = MenuItemBuilder::with_id("import-source", "Import Source…")
        .accelerator("CmdOrCtrl+O")
        .build(app)?;
    let file_menu = SubmenuBuilder::new(app, "File")
        .items(&[&new_conversation, &import_source])
        .separator()
        .close_window()
        .build()?;

    let command_palette = MenuItemBuilder::with_id("command-palette", "Command Palette…")
        .accelerator("CmdOrCtrl+K")
        .build(app)?;
    let learning_feed = MenuItemBuilder::with_id("open-learning-feed", "Learning Feed")
        .accelerator("CmdOrCtrl+Shift+L")
        .build(app)?;
    let view_menu = SubmenuBuilder::new(app, "View")
        .items(&[&command_palette, &learning_feed])
        .separator()
        .fullscreen()
        .build()?;

    let menu = MenuBuilder::new(app)
        .items(&[&application_menu, &file_menu, &view_menu])
        .build()?;
    app.set_menu(menu)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            install_native_menu(app)?;
            let data_dir = app.path().app_data_dir()?;
            let cache_dir = app.path().app_cache_dir()?;
            let sidecar = SidecarSupervisor::new(data_dir.join("learning-core.sqlite3"), cache_dir);
            app.manage(sidecar.clone());
            sidecar.start(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            #[cfg(target_os = "macos")]
            if should_hide_main_window(window.label(), event) {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .on_menu_event(|app, event| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.emit("keen://menu", event.id().as_ref());
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_sidecar_connection,
            get_sidecar_diagnostics,
            restart_sidecar,
            get_provider_configuration,
            save_provider_configuration
        ])
        .build(tauri::generate_context!())
        .expect("failed to build Keen desktop application");

    app.run(|app_handle, event| match application_event_action(&event) {
        ApplicationEventAction::ReopenMainWindow => {
            #[cfg(target_os = "macos")]
            if let Err(error) = reopen_main_window(app_handle) {
                eprintln!("failed to reopen the Keen main window: {error}");
            }
        }
        ApplicationEventAction::ShutdownSidecar => {
            app_handle.state::<SidecarSupervisor>().shutdown();
        }
        ApplicationEventAction::None => {}
    });
}

#[cfg(test)]
mod tests {
    use super::{
        application_event_action, main_window_reopen_action, should_hide_main_window,
        ApplicationEventAction, MainWindowReopenAction,
    };

    #[test]
    fn development_release_and_audit_configs_have_distinct_app_identities() {
        let release: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).expect("release Tauri config");
        let development: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.dev.conf.json"))
                .expect("development Tauri config");
        let audit: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.ui-audit.conf.json"))
                .expect("audit Tauri config");

        assert_eq!(release["identifier"], "com.keen.learning");
        assert_eq!(development["identifier"], "com.keen.learning.dev");
        assert_eq!(audit["identifier"], "com.keen.learning.ui-audit");
        assert_eq!(release["productName"], "Keen");
        assert_eq!(development["app"]["windows"][0]["title"], "Keen Dev");
        assert_eq!(audit["productName"], "Keen UI Audit");
        assert_eq!(audit["app"]["windows"][0]["title"], "Keen UI Audit");
        assert_ne!(release["identifier"], development["identifier"]);
        assert_ne!(release["identifier"], audit["identifier"]);
        assert_ne!(development["identifier"], audit["identifier"]);
        assert_ne!(release["productName"], development["productName"]);
        assert_ne!(release["productName"], audit["productName"]);
        assert_ne!(development["productName"], audit["productName"]);
    }

    #[test]
    fn only_application_exit_events_request_sidecar_shutdown() {
        assert_eq!(
            application_event_action(&tauri::RunEvent::Exit),
            ApplicationEventAction::ShutdownSidecar
        );
        assert_eq!(
            application_event_action(&tauri::RunEvent::Ready),
            ApplicationEventAction::None
        );
        assert!(!should_hide_main_window(
            "main",
            &tauri::WindowEvent::Destroyed
        ));
    }

    #[test]
    fn dock_reopen_shows_or_rebuilds_main_window_without_a_sidecar_action() {
        assert_eq!(
            main_window_reopen_action(true, true),
            MainWindowReopenAction::ShowExisting
        );
        assert_eq!(
            main_window_reopen_action(false, true),
            MainWindowReopenAction::BuildFromConfig
        );
        assert_eq!(
            main_window_reopen_action(false, false),
            MainWindowReopenAction::None
        );
    }
}
