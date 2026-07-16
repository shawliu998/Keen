mod security;
mod sidecar;

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
    let application_menu = SubmenuBuilder::new(app, "Keen")
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

    let new_conversation = MenuItemBuilder::with_id("new-conversation", "New Conversation")
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
            restart_sidecar
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
    fn development_and_release_configs_have_distinct_app_identities() {
        let release: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).expect("release Tauri config");
        let development: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.dev.conf.json"))
                .expect("development Tauri config");

        assert_eq!(release["identifier"], "com.keen.learning");
        assert_eq!(development["identifier"], "com.keen.learning.dev");
        assert_ne!(release["identifier"], development["identifier"]);
        assert_ne!(release["productName"], development["productName"]);
        assert_eq!(development["app"]["windows"][0]["title"], "Keen Dev");
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
