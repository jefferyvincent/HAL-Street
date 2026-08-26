// Hide the console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    halstreet_panel_lib::run()
}
