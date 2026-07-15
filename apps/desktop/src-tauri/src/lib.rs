mod security;

use serde::Serialize;
use std::sync::Mutex;
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder},
    Emitter, Manager, State,
};

#[derive(Debug)]
struct SidecarConnection {
    port: Option<u16>,
    token: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SidecarConnectionView {
    available: bool,
    port: Option<u16>,
    token: Option<String>,
}

#[tauri::command]
fn get_sidecar_connection(state: State<'_, Mutex<SidecarConnection>>) -> SidecarConnectionView {
    let connection = state.lock().expect("sidecar state lock poisoned");
    SidecarConnectionView {
        available: connection.port.is_some(),
        port: connection.port,
        token: connection.port.map(|_| connection.token.clone()),
    }
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
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            install_native_menu(app)?;
            app.manage(Mutex::new(SidecarConnection {
                port: None,
                token: security::generate_session_token(),
            }));
            Ok(())
        })
        .on_menu_event(|app, event| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.emit("keen://menu", event.id().as_ref());
            }
        })
        .invoke_handler(tauri::generate_handler![get_sidecar_connection])
        .run(tauri::generate_context!())
        .expect("failed to run Keen desktop application");
}
