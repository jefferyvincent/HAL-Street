//! The desktop shell for the HAL Street panel.
//!
//! Deliberately empty of commands. Tauri's whole appeal is the bridge it opens
//! between a web view and native code, and that bridge is exactly what this panel
//! must not have: an `#[tauri::command]` here would be a path from a button to the
//! host process, and from there to the broker, that does not pass through `gates/`.
//!
//! So the shell is a window and nothing else. Everything the panel knows it learns
//! from the Python server over HTTP and a send-only WebSocket, the same two routes
//! the browser uses, with the CSP in `tauri.conf.json` pinning it to localhost. The
//! desktop build has no capability the browser build lacks — it is a nicer frame
//! around the identical, unprivileged page.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // No .invoke_handler: there are no commands, and adding one would be the
        // moment this stopped being read-only.
        .run(tauri::generate_context!())
        .expect("error while running HAL Street panel");
}
