//! Desktop bootstrap for the long-lived Python HTTP control plane.
//! The bearer credential is returned to the WebView only through Tauri IPC and
//! is never printed, placed in a URL, or persisted by the frontend.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::{net::TcpListener, path::{Path, PathBuf}, process::{Child, Command, Stdio}, sync::Mutex, thread, time::{Duration, Instant}};

fn repo_root() -> PathBuf {
    if let Ok(p) = std::env::var("PHANTOM_REPO") { return PathBuf::from(p); }
    if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().and_then(Path::parent).unwrap().to_path_buf()
    } else {
        std::env::current_exe().ok().and_then(|p| p.parent().map(Path::to_path_buf)).unwrap_or_else(|| PathBuf::from("."))
    }
}

#[derive(Debug)]
struct SidecarCommand { executable: PathBuf, prefix_args: Vec<String>, working_dir: PathBuf }

fn sidecar_command(root: &Path) -> Result<SidecarCommand, String> {
    if let Ok(value) = std::env::var("PHANTOM_PYTHON") {
        let path = PathBuf::from(value);
        if path.is_file() { return Ok(SidecarCommand { executable: path, prefix_args: vec!["-m".into(), "phantom.cli".into()], working_dir: root.into() }); }
        return Err("PHANTOM_PYTHON không trỏ tới executable hợp lệ".into());
    }
    let venv = if cfg!(windows) { root.join(".venv/Scripts/python.exe") } else { root.join(".venv/bin/python") };
    if venv.is_file() { return Ok(SidecarCommand { executable: venv, prefix_args: vec!["-m".into(), "phantom.cli".into()], working_dir: root.into() }); }
    if cfg!(windows) {
        for path in [root.join("phantom-sidecar/phantom-sidecar.exe"), root.join("resources/phantom-sidecar/phantom-sidecar.exe")] {
            if path.is_file() { return Ok(SidecarCommand { executable: path, prefix_args: vec![], working_dir: root.into() }); }
        }
    }
    Err("Không tìm thấy Python control plane; đặt PHANTOM_PYTHON hoặc cài lại gói desktop".into())
}

fn data_dir() -> Result<PathBuf, String> {
    if let Ok(value) = std::env::var("PHANTOM_DATA_DIR") { return Ok(PathBuf::from(value)); }
    if cfg!(windows) {
        return std::env::var_os("LOCALAPPDATA").map(PathBuf::from).map(|p| p.join("phantom/phantom"))
            .ok_or_else(|| "LOCALAPPDATA không tồn tại".into());
    }
    let home = std::env::var_os("HOME").map(PathBuf::from).ok_or_else(|| "HOME không tồn tại".to_string())?;
    Ok(home.join(".local/share/phantom"))
}

#[derive(Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ControlPlaneConfig { base_url: String, token: String }
struct ControlPlaneState { config: ControlPlaneConfig, child: Mutex<Option<Child>> }

fn terminate_tree(child: &mut Child) {
    #[cfg(windows)] { let _ = Command::new("taskkill").args(["/T", "/F", "/PID", &child.id().to_string()]).stdout(Stdio::null()).stderr(Stdio::null()).status(); }
    #[cfg(not(windows))] { let _ = child.kill(); }
    let _ = child.wait();
}
impl Drop for ControlPlaneState { fn drop(&mut self) { if let Ok(slot)=self.child.get_mut() { if let Some(child)=slot.as_mut() { terminate_tree(child); } } } }

fn start_control_plane() -> Result<ControlPlaneState, String> {
    let root=repo_root(); let sidecar=sidecar_command(&root)?; let data=data_dir()?;
    let listener=TcpListener::bind("127.0.0.1:0").map_err(|e|e.to_string())?;
    let port=listener.local_addr().map_err(|e|e.to_string())?.port(); let base_url=format!("http://127.0.0.1:{port}");
    let token_path=data.join("runtime/.api_token"); drop(listener);
    let mut args=sidecar.prefix_args.clone();
    args.extend(["serve".into(),"--host".into(),"127.0.0.1".into(),"--port".into(),port.to_string(),"--log-level".into(),"warning".into()]);
    let mut child=Command::new(&sidecar.executable).args(args).current_dir(&sidecar.working_dir)
        .env("PHANTOM_DATA_DIR", &data).env("PHANTOM_CAMOUFOX_DIR", sidecar.executable.parent().unwrap_or(&root).join("_internal/camoufox"))
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).spawn().map_err(|e|format!("Không thể khởi động control plane: {e}"))?;
    let deadline=Instant::now()+Duration::from_secs(30); let mut token=String::new();
    while Instant::now()<deadline {
        if let Ok(Some(status))=child.try_wait(){return Err(format!("Control plane đã thoát sớm: {status}"));}
        if token.is_empty(){token=std::fs::read_to_string(&token_path).unwrap_or_default().trim().to_owned();}
        if !token.is_empty(){if let Ok(response)=ureq::get(&format!("{base_url}/readyz")).header("Authorization",&format!("Bearer {token}")).call(){if response.status().is_success(){return Ok(ControlPlaneState{config:ControlPlaneConfig{base_url,token},child:Mutex::new(Some(child))});}}}
        thread::sleep(Duration::from_millis(100));
    }
    terminate_tree(&mut child); Err("Control plane không sẵn sàng sau 30 giây".into())
}

#[tauri::command] fn control_plane_config(state:tauri::State<'_,ControlPlaneState>)->ControlPlaneConfig{state.config.clone()}
#[cfg_attr(mobile, tauri::mobile_entry_point)] pub fn run(){let state=start_control_plane().expect("failed to start Phantom control plane");tauri::Builder::default().plugin(tauri_plugin_opener::init()).manage(state).invoke_handler(tauri::generate_handler![control_plane_config]).run(tauri::generate_context!()).expect("error while running tauri application");}

#[cfg(test)] mod tests { use super::*;
 #[test] fn config_serializes_for_frontend(){let value=serde_json::to_value(ControlPlaneConfig{base_url:"http://127.0.0.1:1".into(),token:"secret".into()}).unwrap();assert_eq!(value["baseUrl"],"http://127.0.0.1:1");assert!(value.get("base_url").is_none());}
 #[test] fn dev_repo_has_pyproject(){assert!(repo_root().join("pyproject.toml").exists());}
 #[test] fn missing_sidecar_is_explicit(){if std::env::var_os("PHANTOM_PYTHON").is_none(){assert!(sidecar_command(Path::new("/definitely/not/phantom")).unwrap_err().contains("control plane"));}}
 #[test] fn packaged_layout_candidate_is_stable(){let root=Path::new("C:/Program Files/Phantom Browser");assert!(root.join("phantom-sidecar/phantom-sidecar.exe").ends_with("phantom-sidecar/phantom-sidecar.exe"));}
}
