mod security;
mod sidecar;

use sidecar::{SidecarConnectionView, SidecarSupervisor};
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder},
    Emitter, Manager, State,
};

#[tauri::command]
fn get_sidecar_connection(state: State<'_, SidecarSupervisor>) -> SidecarConnectionView {
    state.connection_view()
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
            if window.label() == "main" && matches!(event, tauri::WindowEvent::Destroyed) {
                window.state::<SidecarSupervisor>().shutdown();
            }
        })
        .on_menu_event(|app, event| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.emit("keen://menu", event.id().as_ref());
            }
        })
        .invoke_handler(tauri::generate_handler![get_sidecar_connection])
        .build(tauri::generate_context!())
        .expect("failed to build Keen desktop application");

    app.run(|app_handle, event| {
        if matches!(
            event,
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
        ) {
            app_handle.state::<SidecarSupervisor>().shutdown();
        }
    });
}
