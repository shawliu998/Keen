use crate::security::{canonicalize_within, generate_session_token};
use serde::Serialize;
#[cfg(unix)]
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::{
    ffi::OsString,
    io::{self, BufRead, BufReader, Read, Write},
    net::{Ipv4Addr, SocketAddr, SocketAddrV4, TcpStream},
    path::{Path, PathBuf},
    process::{Command as StdCommand, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex, MutexGuard,
    },
    thread,
    time::Duration,
};
use tauri::{AppHandle, Runtime};
use tauri_plugin_shell::ShellExt;
use thiserror::Error;

const SIDECAR_NAME: &str = "keen-learning-core";
const DATABASE_FILE_NAME: &str = "learning-core.sqlite3";
const DOCUMENTS_DIRECTORY_NAME: &str = "documents";
const SIDECAR_TEMP_DIRECTORY_NAME: &str = "sidecar-tmp";
const MAX_RESTARTS: u8 = 1;
const RESTART_DELAY: Duration = Duration::from_millis(300);
const HEALTH_CONFIRMATION_TIMEOUT: Duration = Duration::from_secs(10);
const HEALTH_INTERVAL: Duration = Duration::from_millis(250);
const HEALTH_IO_TIMEOUT: Duration = Duration::from_millis(350);
const STEADY_HEALTH_INTERVAL: Duration = Duration::from_secs(5);
const STEADY_HEALTH_FAILURE_LIMIT: u8 = 3;
const TERMINATION_GRACE_TIMEOUT: Duration = Duration::from_millis(1_500);
const FORCE_KILL_WAIT_TIMEOUT: Duration = Duration::from_secs(2);
const PORT_ANNOUNCEMENT_TIMEOUT: Duration = Duration::from_secs(10);
const READY_ANNOUNCEMENT_TIMEOUT: Duration = Duration::from_secs(90);
const SUPERVISOR_PID_ENVIRONMENT_KEY: &str = "KEEN_SUPERVISOR_PID";
const PORT_ANNOUNCEMENT_PREFIX: &str = "KEEN_SIDECAR_PORT=";
const PHASE_ANNOUNCEMENT_PREFIX: &str = "KEEN_SIDECAR_PHASE=";
const READY_ANNOUNCEMENT: &str = "KEEN_SIDECAR_READY=1";
const SEED_DEMO_ENVIRONMENT_KEY: &str = "KEEN_SEED_DEMO";
const EMBEDDING_PROVIDER_ENVIRONMENT_KEY: &str = "KEEN_EMBEDDING_PROVIDER";
const EMBEDDING_BASE_URL_ENVIRONMENT_KEY: &str = "KEEN_EMBEDDING_BASE_URL";
const EMBEDDING_MODEL_ENVIRONMENT_KEY: &str = "KEEN_EMBEDDING_MODEL";
const EMBEDDING_VERSION_ENVIRONMENT_KEY: &str = "KEEN_EMBEDDING_VERSION";
const EMBEDDING_DIMENSIONS_ENVIRONMENT_KEY: &str = "KEEN_EMBEDDING_DIMENSIONS";
const CHAT_PROVIDER_ENVIRONMENT_KEY: &str = "KEEN_CHAT_PROVIDER";
const CHAT_BASE_URL_ENVIRONMENT_KEY: &str = "KEEN_CHAT_BASE_URL";
const CHAT_MODEL_ENVIRONMENT_KEY: &str = "KEEN_CHAT_MODEL";
const CHAT_VERSION_ENVIRONMENT_KEY: &str = "KEEN_CHAT_VERSION";
const MAX_PROCESS_OUTPUT_LINE_BYTES: usize = 64 * 1024;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SidecarStatus {
    Stopped,
    Starting,
    Restarting,
    Ready,
    Unavailable,
    ConfigurationError,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SidecarPhase {
    Binding,
    Migrating,
    Recovering,
    StartingServer,
    HealthChecking,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SidecarConnectionView {
    available: bool,
    port: Option<u16>,
    base_url: Option<String>,
    token: Option<String>,
    status: SidecarStatus,
    phase: Option<SidecarPhase>,
    message: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SidecarDiagnosticsView {
    status: SidecarStatus,
    phase: Option<SidecarPhase>,
    generation: Option<u64>,
    automatic_restarts_used: u8,
    automatic_restarts_maximum: u8,
    launch_in_progress: bool,
    shutting_down: bool,
    last_failure: Option<String>,
    last_restart_reason: Option<String>,
}

#[derive(Clone)]
struct Endpoint {
    port: u16,
    token: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ManagedProcess {
    leader_pid: u32,
    process_group_id: u32,
}

#[derive(Debug)]
enum ManagedProcessEvent {
    Stdout(Vec<u8>),
    Stderr(Vec<u8>),
    Error(String),
    Terminated {
        code: Option<i32>,
        signal: Option<i32>,
    },
}

struct SupervisorState {
    status: SidecarStatus,
    phase: Option<SidecarPhase>,
    message: Option<String>,
    endpoint: Option<Endpoint>,
    child: Option<ManagedProcess>,
    termination_waiter: Option<mpsc::Receiver<()>>,
    generation_temporary_path: Option<PathBuf>,
    next_generation: u64,
    active_generation: Option<u64>,
    launch_in_progress: bool,
    shutting_down: bool,
    restart_policy: RestartPolicy,
    last_failure: Option<String>,
    last_restart_reason: Option<String>,
}

struct ManualRestartResources {
    child: Option<ManagedProcess>,
    termination_waiter: Option<mpsc::Receiver<()>>,
    generation_temporary_path: Option<PathBuf>,
}

enum ManualRestartPreparation {
    Rejected(&'static str),
    Idempotent(SidecarConnectionView),
    Begin(ManualRestartResources),
}

impl Default for SupervisorState {
    fn default() -> Self {
        Self {
            status: SidecarStatus::Stopped,
            phase: None,
            message: None,
            endpoint: None,
            child: None,
            termination_waiter: None,
            generation_temporary_path: None,
            next_generation: 0,
            active_generation: None,
            launch_in_progress: false,
            shutting_down: false,
            restart_policy: RestartPolicy::new(MAX_RESTARTS),
            last_failure: None,
            last_restart_reason: None,
        }
    }
}

#[derive(Clone)]
pub struct SidecarSupervisor {
    inner: Arc<Mutex<SupervisorState>>,
    lifecycle_gate: Arc<Mutex<()>>,
    shutdown_requested: Arc<AtomicBool>,
    database_path: PathBuf,
    temporary_path: PathBuf,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum FailureAction {
    Restart,
    Stop,
    Unavailable,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct RestartPolicy {
    maximum: u8,
    used: u8,
}

impl RestartPolicy {
    const fn new(maximum: u8) -> Self {
        Self { maximum, used: 0 }
    }

    fn after_failure(&mut self, shutting_down: bool) -> FailureAction {
        if shutting_down {
            FailureAction::Stop
        } else if self.used < self.maximum {
            self.used += 1;
            FailureAction::Restart
        } else {
            FailureAction::Unavailable
        }
    }
}

#[derive(Debug)]
struct SidecarArguments {
    database_path: PathBuf,
    documents_path: PathBuf,
    seed_demo: bool,
    embedding: Option<EmbeddingArguments>,
    chat: Option<ChatArguments>,
}

#[derive(Debug)]
struct EmbeddingArguments {
    provider: OsString,
    base_url: OsString,
    model: OsString,
    version: OsString,
    dimensions: OsString,
}

#[derive(Debug)]
struct ChatArguments {
    provider: OsString,
    base_url: OsString,
    model: OsString,
    version: OsString,
}

impl SidecarArguments {
    fn into_os_strings(self) -> Vec<OsString> {
        let mut arguments = vec![
            OsString::from("--token-stdin"),
            OsString::from("--port"),
            OsString::from("0"),
            OsString::from("--database"),
            self.database_path.into_os_string(),
            OsString::from("--documents-directory"),
            self.documents_path.into_os_string(),
        ];
        if self.seed_demo {
            arguments.push(OsString::from("--seed-demo"));
        }
        if let Some(embedding) = self.embedding {
            arguments.extend([
                OsString::from("--embedding-provider"),
                embedding.provider,
                OsString::from("--embedding-base-url"),
                embedding.base_url,
                OsString::from("--embedding-model"),
                embedding.model,
                OsString::from("--embedding-version"),
                embedding.version,
                OsString::from("--embedding-dimensions"),
                embedding.dimensions,
            ]);
        }
        if let Some(chat) = self.chat {
            arguments.extend([
                OsString::from("--chat-provider"),
                chat.provider,
                OsString::from("--chat-base-url"),
                chat.base_url,
                OsString::from("--chat-model"),
                chat.model,
                OsString::from("--chat-version"),
                chat.version,
            ]);
        }
        arguments
    }
}

#[derive(Debug)]
enum LaunchProgram {
    Bundled,
    Development {
        python: PathBuf,
        service_root: PathBuf,
    },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LifecycleEvent {
    Port(u16),
    Phase(SidecarPhase),
    Ready,
}

#[derive(Debug, Error)]
enum SidecarError {
    #[error("failed to prepare the learning-core data directory")]
    DataDirectory(#[source] io::Error),
    #[error("the learning-core database path escaped its application data directory")]
    DatabaseBoundary,
    #[error("the learning-core documents path escaped its application data directory")]
    DocumentsBoundary,
    #[error("the learning-core temporary path escaped its application cache directory")]
    TemporaryBoundary,
    #[error("the fixed development learning-core runtime is unavailable")]
    DevelopmentRuntimeUnavailable,
    #[error("the local embedding provider configuration is incomplete")]
    EmbeddingConfiguration,
    #[error("the local chat provider configuration is incomplete")]
    ChatConfiguration,
    #[error("failed to resolve the bundled learning-core sidecar")]
    BundledCommand(#[source] tauri_plugin_shell::Error),
    #[error("failed to launch the bundled learning-core sidecar")]
    BundledLaunch(#[source] io::Error),
    #[error("failed to launch the development learning-core sidecar")]
    DevelopmentLaunch(#[source] io::Error),
}

impl SidecarError {
    fn is_configuration_error(&self) -> bool {
        matches!(
            self,
            Self::DataDirectory(_)
                | Self::DatabaseBoundary
                | Self::DocumentsBoundary
                | Self::TemporaryBoundary
                | Self::EmbeddingConfiguration
                | Self::ChatConfiguration
                | Self::DevelopmentRuntimeUnavailable
                | Self::BundledCommand(_)
        )
    }

    fn user_message(&self) -> &'static str {
        match self {
            Self::DataDirectory(_)
            | Self::DatabaseBoundary
            | Self::DocumentsBoundary
            | Self::TemporaryBoundary => {
                "Keen could not prepare its private local learning data. Check the app data permissions, then restart Keen."
            }
            Self::DevelopmentRuntimeUnavailable => {
                "The local development learning service is not installed. Restore the project Python environment, then retry."
            }
            Self::EmbeddingConfiguration => {
                "The local embedding provider configuration is incomplete. Set all KEEN_EMBEDDING_* values or remove them, then restart Keen."
            }
            Self::ChatConfiguration => {
                "The local chat provider configuration is incomplete. Set all KEEN_CHAT_* values or remove them, then restart Keen."
            }
            Self::BundledCommand(_) => {
                "The packaged learning service could not be resolved. Reinstall Keen, then retry."
            }
            Self::BundledLaunch(_) | Self::DevelopmentLaunch(_) => {
                "The local learning service could not be launched. Retry once; if it still fails, restart Keen."
            }
        }
    }
}

impl SidecarSupervisor {
    pub fn new(database_path: PathBuf, cache_directory: PathBuf) -> Self {
        Self {
            inner: Arc::new(Mutex::new(SupervisorState::default())),
            lifecycle_gate: Arc::new(Mutex::new(())),
            shutdown_requested: Arc::new(AtomicBool::new(false)),
            database_path,
            temporary_path: cache_directory.join(SIDECAR_TEMP_DIRECTORY_NAME),
        }
    }

    pub fn connection_view(&self) -> SidecarConnectionView {
        let state = self.lock();
        let endpoint = (state.status == SidecarStatus::Ready)
            .then_some(state.endpoint.as_ref())
            .flatten();
        SidecarConnectionView {
            available: endpoint.is_some(),
            port: endpoint.map(|value| value.port),
            base_url: endpoint.map(|value| loopback_base_url(value.port)),
            token: endpoint.map(|value| value.token.clone()),
            status: state.status,
            phase: state.phase,
            message: state.message.clone(),
        }
    }

    pub fn diagnostics_view(&self) -> SidecarDiagnosticsView {
        let state = self.lock();
        SidecarDiagnosticsView {
            status: state.status,
            phase: state.phase,
            generation: state.active_generation,
            automatic_restarts_used: state.restart_policy.used,
            automatic_restarts_maximum: state.restart_policy.maximum,
            launch_in_progress: state.launch_in_progress,
            shutting_down: self.shutdown_is_requested() || state.shutting_down,
            last_failure: state.last_failure.clone(),
            last_restart_reason: state.last_restart_reason.clone(),
        }
    }

    pub fn start<R: Runtime>(&self, app: AppHandle<R>) {
        let _lifecycle = self.lock_lifecycle();
        {
            let mut state = self.lock();
            if self.shutdown_is_requested()
                || state.launch_in_progress
                || state.active_generation.is_some()
            {
                return;
            }
            state.restart_policy = RestartPolicy::new(MAX_RESTARTS);
            state.status = SidecarStatus::Starting;
            state.phase = Some(SidecarPhase::Binding);
            state.message = None;
            state.launch_in_progress = true;
        }
        self.schedule_launch(app, Duration::ZERO);
    }

    pub fn restart<R: Runtime>(
        &self,
        app: AppHandle<R>,
        reason: Option<String>,
    ) -> Result<SidecarConnectionView, String> {
        if self.shutdown_is_requested() {
            return Err("the application is exiting; learning-core restart was refused".into());
        }
        let _lifecycle = self.lock_lifecycle();
        if self.shutdown_is_requested() {
            return Err("the application is exiting; learning-core restart was refused".into());
        }
        let reason = normalized_restart_reason(reason.as_deref());
        let preparation = {
            let mut state = self.lock();
            prepare_manual_restart_state(&mut state, reason)
        };
        let ManualRestartResources {
            child,
            termination_waiter,
            generation_temporary_path,
        } = match preparation {
            ManualRestartPreparation::Rejected(message) => return Err(message.to_owned()),
            ManualRestartPreparation::Idempotent(view) => return Ok(view),
            ManualRestartPreparation::Begin(resources) => resources,
        };

        if !terminate_child(child, termination_waiter) {
            let mut state = self.lock();
            state.status = SidecarStatus::Unavailable;
            state.message = Some(
                "The previous learning service process tree could not be stopped; no replacement was started."
                    .to_owned(),
            );
            state.last_failure = state.message.clone();
            return Err(state.message.clone().unwrap_or_default());
        }
        if let Some(path) = generation_temporary_path {
            remove_generation_temporary_path(&path);
        }

        {
            let mut state = self.lock();
            if self.shutdown_is_requested() || state.shutting_down {
                state.status = SidecarStatus::Stopped;
                state.phase = None;
                state.message = Some(
                    "The application began exiting before the learning service could restart."
                        .to_owned(),
                );
                return Err(state.message.clone().unwrap_or_default());
            }
            state.restart_policy = RestartPolicy::new(MAX_RESTARTS);
            state.status = SidecarStatus::Restarting;
            state.phase = Some(SidecarPhase::Binding);
            state.message = None;
            state.launch_in_progress = true;
        }
        self.schedule_launch(app, Duration::ZERO);
        Ok(self.connection_view())
    }

    pub fn shutdown(&self) {
        self.shutdown_requested.store(true, Ordering::SeqCst);
        let _lifecycle = self.lock_lifecycle();
        let (child, termination_waiter, generation_temporary_path) = {
            let mut state = self.lock();
            state.shutting_down = true;
            state.launch_in_progress = false;
            state.active_generation = None;
            state.endpoint = None;
            state.status = SidecarStatus::Stopped;
            state.phase = None;
            state.message = None;
            (
                state.child.take(),
                state.termination_waiter.take(),
                state.generation_temporary_path.take(),
            )
        };
        if terminate_child(child, termination_waiter) {
            // Application shutdown can tear down the async runtime before a delayed cleanup
            // thread runs. Once the entire isolated process group is gone, remove this
            // generation synchronously so a normal quit cannot strand a PyInstaller tree.
            if let Some(path) = generation_temporary_path {
                remove_generation_temporary_path(&path);
            }
        } else {
            eprintln!(
                "learning-core process group survived shutdown; preserving its temporary directory"
            );
        }
    }

    fn lock(&self) -> MutexGuard<'_, SupervisorState> {
        self.inner
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    fn lock_lifecycle(&self) -> MutexGuard<'_, ()> {
        self.lifecycle_gate
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    fn shutdown_is_requested(&self) -> bool {
        self.shutdown_requested.load(Ordering::SeqCst)
    }

    fn schedule_launch<R: Runtime>(&self, app: AppHandle<R>, delay: Duration) {
        let supervisor = self.clone();
        tauri::async_runtime::spawn_blocking(move || {
            if supervisor.shutdown_is_requested() {
                return;
            }
            if !delay.is_zero() {
                thread::sleep(delay);
            }
            if supervisor.shutdown_is_requested() {
                return;
            }
            supervisor.launch_once(app);
        });
    }

    fn launch_once<R: Runtime>(&self, app: AppHandle<R>) {
        let _lifecycle = self.lock_lifecycle();
        if !self.should_continue_launch() {
            return;
        }

        let launch = self.prepare_and_spawn(&app);
        let (receiver, child, token, generation_temporary_path) = match launch {
            Ok(spawned) => spawned,
            Err(error) => {
                eprintln!("learning-core sidecar launch failed: {error:?}");
                let configuration_error = error.is_configuration_error();
                self.handle_launch_failure(app, error.user_message(), configuration_error);
                return;
            }
        };

        let (termination_sender, termination_waiter) = mpsc::sync_channel(1);
        let (endpoint_sender, endpoint_waiter) = mpsc::sync_channel(1);
        let (ready_sender, ready_waiter) = mpsc::sync_channel(1);
        let generation = {
            let mut state = self.lock();
            if self.shutdown_is_requested() || state.shutting_down || !state.launch_in_progress {
                drop(state);
                if terminate_unmanaged_child(child) {
                    remove_generation_temporary_path(&generation_temporary_path);
                }
                return;
            }
            state.next_generation = state.next_generation.wrapping_add(1);
            let generation = state.next_generation;
            state.active_generation = Some(generation);
            state.endpoint = None;
            state.phase = Some(SidecarPhase::Binding);
            state.child = Some(child);
            state.termination_waiter = Some(termination_waiter);
            state.generation_temporary_path = Some(generation_temporary_path);
            state.launch_in_progress = false;
            generation
        };

        let event_supervisor = self.clone();
        let event_app = app.clone();
        tauri::async_runtime::spawn_blocking(move || {
            let mut endpoint_sender = Some(endpoint_sender);
            let mut ready_sender = Some(ready_sender);
            while let Ok(event) = receiver.recv() {
                match event {
                    ManagedProcessEvent::Stdout(line) => match parse_lifecycle_event(&line) {
                        Some(LifecycleEvent::Port(port)) => {
                            let endpoint = Endpoint {
                                port,
                                token: token.clone(),
                            };
                            if event_supervisor.register_endpoint(generation, endpoint.clone()) {
                                if let Some(sender) = endpoint_sender.take() {
                                    let _ = sender.send(endpoint);
                                }
                            }
                        }
                        Some(LifecycleEvent::Phase(phase)) => {
                            event_supervisor.register_phase(generation, phase);
                        }
                        Some(LifecycleEvent::Ready) => {
                            if event_supervisor.register_ready_signal(generation) {
                                if let Some(sender) = ready_sender.take() {
                                    let _ = sender.send(());
                                }
                            }
                        }
                        None => log_sidecar_stdout(&line),
                    },
                    ManagedProcessEvent::Stderr(line) => log_sidecar_stderr(&line),
                    ManagedProcessEvent::Error(error) => {
                        eprintln!(
                            "learning-core sidecar event error: {}",
                            sanitize_log_text(&error)
                        );
                        event_supervisor.record_generation_failure(
                            generation,
                            "The learning service output stream failed or exceeded its safety limit, so the process was stopped.",
                        );
                        event_supervisor.handle_active_failure(event_app, generation);
                        return;
                    }
                    ManagedProcessEvent::Terminated { code, signal } => {
                        eprintln!(
                            "learning-core sidecar terminated: code={:?} signal={:?}",
                            code, signal
                        );
                        let _ = termination_sender.send(());
                        event_supervisor.record_generation_failure(
                            generation,
                            "The learning service process exited unexpectedly.",
                        );
                        event_supervisor.handle_active_failure(event_app, generation);
                        return;
                    }
                }
            }
            let _ = termination_sender.send(());
            event_supervisor.record_generation_failure(
                generation,
                "The learning service event stream ended unexpectedly.",
            );
            event_supervisor.handle_active_failure(event_app, generation);
        });

        let health_supervisor = self.clone();
        tauri::async_runtime::spawn_blocking(move || {
            let endpoint = match endpoint_waiter.recv_timeout(PORT_ANNOUNCEMENT_TIMEOUT) {
                Ok(endpoint) => endpoint,
                Err(_) => {
                    health_supervisor.record_generation_failure(
                        generation,
                        "The learning service did not announce a loopback port within 10 seconds.",
                    );
                    health_supervisor.handle_active_failure(app, generation);
                    return;
                }
            };
            if ready_waiter
                .recv_timeout(READY_ANNOUNCEMENT_TIMEOUT)
                .is_err()
            {
                health_supervisor.record_generation_failure(
                    generation,
                    "The learning service did not finish migration and recovery within 90 seconds.",
                );
                health_supervisor.handle_active_failure(app, generation);
                return;
            }

            let health_deadline = std::time::Instant::now() + HEALTH_CONFIRMATION_TIMEOUT;
            loop {
                if !health_supervisor.is_generation_active(generation) {
                    return;
                }
                if probe_health(endpoint.port, &endpoint.token) {
                    health_supervisor.mark_ready(generation);
                    let mut consecutive_failures = 0_u8;
                    loop {
                        thread::sleep(STEADY_HEALTH_INTERVAL);
                        if !health_supervisor.is_generation_active(generation) {
                            return;
                        }
                        if probe_health(endpoint.port, &endpoint.token) {
                            consecutive_failures = 0;
                            continue;
                        }
                        consecutive_failures += 1;
                        if consecutive_failures >= STEADY_HEALTH_FAILURE_LIMIT {
                            health_supervisor.record_generation_failure(
                                generation,
                                "The learning service stopped passing authenticated health checks and will be restarted if the automatic retry budget allows.",
                            );
                            health_supervisor.handle_active_failure(app, generation);
                            return;
                        }
                    }
                }
                if std::time::Instant::now() >= health_deadline {
                    health_supervisor.record_generation_failure(
                        generation,
                        "The learning service announced readiness but authenticated health did not succeed within 10 seconds.",
                    );
                    health_supervisor.handle_active_failure(app, generation);
                    return;
                }
                thread::sleep(HEALTH_INTERVAL);
            }
        });
    }

    fn should_continue_launch(&self) -> bool {
        let state = self.lock();
        !self.shutdown_is_requested()
            && state.launch_in_progress
            && !state.shutting_down
            && state.active_generation.is_none()
    }

    fn prepare_and_spawn<R: Runtime>(
        &self,
        app: &AppHandle<R>,
    ) -> Result<
        (
            mpsc::Receiver<ManagedProcessEvent>,
            ManagedProcess,
            String,
            PathBuf,
        ),
        SidecarError,
    > {
        let database_path = prepare_database_path(&self.database_path)?;
        let documents_path = prepare_documents_path(&database_path)?;
        let launch_program = launch_program()?;
        let temporary_path = prepare_temporary_path(&self.temporary_path)?;
        let token = new_session_token();
        let arguments = SidecarArguments {
            database_path,
            documents_path,
            seed_demo: seed_demo_requested(std::env::var_os(SEED_DEMO_ENVIRONMENT_KEY).as_deref()),
            embedding: embedding_arguments_from_environment()?,
            chat: chat_arguments_from_environment()?,
        }
        .into_os_strings();

        let spawn_result = match launch_program {
            LaunchProgram::Bundled => {
                let command = match app.shell().sidecar(SIDECAR_NAME) {
                    Ok(command) => command,
                    Err(source) => {
                        remove_generation_temporary_path(&temporary_path);
                        return Err(SidecarError::BundledCommand(source));
                    }
                };
                let command = command
                    .env_clear()
                    .env(
                        SUPERVISOR_PID_ENVIRONMENT_KEY,
                        std::process::id().to_string(),
                    )
                    .env("TMPDIR", &temporary_path)
                    .args(arguments);
                spawn_managed_process(command.into(), &token)
                    .map(|spawned| (spawned, true))
                    .map_err(SidecarError::BundledLaunch)
            }
            LaunchProgram::Development {
                python,
                service_root,
            } => {
                let command = app
                    .shell()
                    .command(python)
                    .env_clear()
                    .env(
                        SUPERVISOR_PID_ENVIRONMENT_KEY,
                        std::process::id().to_string(),
                    )
                    .env("PYTHONNOUSERSITE", "1")
                    .env("PYTHONUNBUFFERED", "1")
                    .env("TMPDIR", &temporary_path)
                    .current_dir(service_root)
                    .args([OsString::from("-m"), OsString::from("app")])
                    .args(arguments);
                spawn_managed_process(command.into(), &token)
                    .map(|spawned| (spawned, false))
                    .map_err(SidecarError::DevelopmentLaunch)
            }
        };
        let ((receiver, child), _bundled) = match spawn_result {
            Ok(spawned) => spawned,
            Err(error) => {
                remove_generation_temporary_path(&temporary_path);
                return Err(error);
            }
        };
        Ok((receiver, child, token, temporary_path))
    }

    fn register_endpoint(&self, generation: u64, endpoint: Endpoint) -> bool {
        let mut state = self.lock();
        if state.active_generation == Some(generation)
            && state.endpoint.is_none()
            && !self.shutdown_is_requested()
            && !state.shutting_down
        {
            state.endpoint = Some(endpoint);
            true
        } else {
            false
        }
    }

    fn register_phase(&self, generation: u64, phase: SidecarPhase) -> bool {
        let mut state = self.lock();
        let valid_transition = matches!(
            (state.phase, phase),
            (Some(SidecarPhase::Binding), SidecarPhase::Migrating)
                | (Some(SidecarPhase::Migrating), SidecarPhase::Recovering)
                | (Some(SidecarPhase::Recovering), SidecarPhase::StartingServer)
        );
        if state.active_generation == Some(generation)
            && state.endpoint.is_some()
            && !self.shutdown_is_requested()
            && !state.shutting_down
            && valid_transition
        {
            state.phase = Some(phase);
            true
        } else {
            false
        }
    }

    fn register_ready_signal(&self, generation: u64) -> bool {
        let mut state = self.lock();
        if state.active_generation == Some(generation)
            && state.endpoint.is_some()
            && state.phase == Some(SidecarPhase::StartingServer)
            && !self.shutdown_is_requested()
            && !state.shutting_down
        {
            state.phase = Some(SidecarPhase::HealthChecking);
            true
        } else {
            false
        }
    }

    fn mark_ready(&self, generation: u64) {
        let mut state = self.lock();
        if state.active_generation == Some(generation)
            && state.phase == Some(SidecarPhase::HealthChecking)
            && !self.shutdown_is_requested()
            && !state.shutting_down
        {
            state.status = SidecarStatus::Ready;
            state.phase = None;
            state.message = None;
        }
    }

    fn record_generation_failure(&self, generation: u64, message: &str) {
        let mut state = self.lock();
        if state.active_generation == Some(generation) && !self.shutdown_is_requested() {
            let message = sanitize_log_text(message);
            state.message = Some(message.clone());
            state.last_failure = Some(message);
        }
    }

    fn is_generation_active(&self, generation: u64) -> bool {
        let state = self.lock();
        state.active_generation == Some(generation)
            && !self.shutdown_is_requested()
            && !state.shutting_down
    }

    fn handle_launch_failure<R: Runtime>(
        &self,
        app: AppHandle<R>,
        message: &str,
        configuration_error: bool,
    ) {
        let action = {
            let mut state = self.lock();
            if self.shutdown_is_requested() || state.shutting_down || !state.launch_in_progress {
                return;
            }
            state.launch_in_progress = false;
            state.endpoint = None;
            state.phase = None;
            let message = message.to_owned();
            state.message = Some(message.clone());
            state.last_failure = Some(message);
            if configuration_error {
                state.status = SidecarStatus::ConfigurationError;
                return;
            }
            let shutting_down = self.shutdown_is_requested() || state.shutting_down;
            let action = state.restart_policy.after_failure(shutting_down);
            apply_failure_action(&mut state, action);
            action
        };
        if action == FailureAction::Restart && !self.shutdown_is_requested() {
            self.schedule_launch(app, RESTART_DELAY);
        }
    }

    fn handle_active_failure<R: Runtime>(&self, app: AppHandle<R>, generation: u64) {
        let _lifecycle = self.lock_lifecycle();
        let (child, termination_waiter, generation_temporary_path, action) = {
            let mut state = self.lock();
            if state.active_generation != Some(generation) {
                return;
            }
            state.active_generation = None;
            state.endpoint = None;
            state.phase = None;
            let child = state.child.take();
            let termination_waiter = state.termination_waiter.take();
            let generation_temporary_path = state.generation_temporary_path.take();
            let shutting_down = self.shutdown_is_requested() || state.shutting_down;
            let action = state.restart_policy.after_failure(shutting_down);
            apply_failure_action(&mut state, action);
            (child, termination_waiter, generation_temporary_path, action)
        };

        if !terminate_child(child, termination_waiter) {
            eprintln!(
                "learning-core process group survived forced termination; preserving its temporary directory"
            );
            if action == FailureAction::Restart {
                let mut state = self.lock();
                if state.active_generation.is_none() && !state.shutting_down {
                    state.status = SidecarStatus::Unavailable;
                    state.launch_in_progress = false;
                    let message = "The learning service process tree could not be stopped, so automatic restart was cancelled.".to_owned();
                    state.message = Some(message.clone());
                    state.last_failure = Some(message);
                }
            }
            return;
        }
        if let Some(path) = generation_temporary_path {
            remove_generation_temporary_path(&path);
        }
        if action == FailureAction::Restart && !self.shutdown_is_requested() {
            self.schedule_launch(app, RESTART_DELAY);
        }
    }
}

fn log_sidecar_stderr(line: &[u8]) {
    let text = String::from_utf8_lossy(line);
    eprintln!("learning-core sidecar stderr: {}", sanitize_log_text(&text));
}

fn log_sidecar_stdout(line: &[u8]) {
    let text = String::from_utf8_lossy(line);
    eprintln!("learning-core sidecar stdout: {}", sanitize_log_text(&text));
}

fn sanitize_log_text(text: &str) -> String {
    let mut sanitized = String::with_capacity(text.len().min(2_048));
    for character in text.chars().take(2_048) {
        match character {
            '\n' => sanitized.push_str("\\n"),
            '\r' => sanitized.push_str("\\r"),
            '\t' => sanitized.push_str("\\t"),
            character if character.is_control() => sanitized.push('\u{fffd}'),
            character => sanitized.push(character),
        }
    }
    sanitized.trim_end().to_owned()
}

fn apply_failure_action(state: &mut SupervisorState, action: FailureAction) {
    match action {
        FailureAction::Restart => {
            state.status = SidecarStatus::Restarting;
            state.phase = Some(SidecarPhase::Binding);
            state.launch_in_progress = true;
        }
        FailureAction::Stop => {
            state.status = SidecarStatus::Stopped;
            state.phase = None;
            state.launch_in_progress = false;
        }
        FailureAction::Unavailable => {
            state.status = SidecarStatus::Unavailable;
            state.phase = None;
            state.launch_in_progress = false;
        }
    }
}

fn spawn_managed_process(
    mut command: StdCommand,
    token: &str,
) -> io::Result<(mpsc::Receiver<ManagedProcessEvent>, ManagedProcess)> {
    configure_managed_process(&mut command, token)?;
    let mut child = command.spawn()?;
    let process = ManagedProcess {
        leader_pid: child.id(),
        process_group_id: child.id(),
    };

    let stdout = child
        .stdout
        .take()
        .expect("managed sidecar stdout was configured as piped");
    let stderr = child
        .stderr
        .take()
        .expect("managed sidecar stderr was configured as piped");
    let (sender, receiver) = mpsc::channel();
    let stdout_thread = spawn_process_output_reader(
        stdout,
        sender.clone(),
        ManagedProcessEvent::Stdout,
        "stdout",
    );
    let stderr_thread = spawn_process_output_reader(
        stderr,
        sender.clone(),
        ManagedProcessEvent::Stderr,
        "stderr",
    );
    thread::spawn(move || {
        match child.wait() {
            Ok(status) => {
                #[cfg(unix)]
                let signal = status.signal();
                #[cfg(not(unix))]
                let signal = None;
                let _ = sender.send(ManagedProcessEvent::Terminated {
                    code: status.code(),
                    signal,
                });
            }
            Err(error) => {
                let _ = sender.send(ManagedProcessEvent::Error(error.to_string()));
            }
        }
        let _ = stdout_thread.join();
        let _ = stderr_thread.join();
    });
    Ok((receiver, process))
}

fn spawn_process_output_reader<R, F>(
    stream: R,
    sender: mpsc::Sender<ManagedProcessEvent>,
    wrap: F,
    stream_name: &'static str,
) -> thread::JoinHandle<()>
where
    R: Read + Send + 'static,
    F: Fn(Vec<u8>) -> ManagedProcessEvent + Send + 'static,
{
    thread::spawn(move || {
        let mut reader = BufReader::new(stream);
        loop {
            let mut line = Vec::new();
            let read_result = reader
                .by_ref()
                .take((MAX_PROCESS_OUTPUT_LINE_BYTES + 1) as u64)
                .read_until(b'\n', &mut line);
            match read_result {
                Ok(0) => return,
                Ok(_) if line.len() > MAX_PROCESS_OUTPUT_LINE_BYTES => {
                    let _ = sender.send(ManagedProcessEvent::Error(format!(
                        "learning-core {stream_name} line exceeded {MAX_PROCESS_OUTPUT_LINE_BYTES} bytes"
                    )));
                    return;
                }
                Ok(_) => {
                    if sender.send(wrap(line)).is_err() {
                        return;
                    }
                }
                Err(error) => {
                    let _ = sender.send(ManagedProcessEvent::Error(error.to_string()));
                    return;
                }
            }
        }
    })
}

#[cfg(unix)]
fn configure_managed_process(command: &mut StdCommand, token: &str) -> io::Result<()> {
    use std::{net::Shutdown, os::fd::OwnedFd, os::unix::net::UnixStream};

    let (mut token_writer, token_reader) = UnixStream::pair()?;
    token_writer.write_all(format!("{token}\n").as_bytes())?;
    token_writer.shutdown(Shutdown::Write)?;
    let token_reader: OwnedFd = token_reader.into();
    command
        .process_group(0)
        .stdin(Stdio::from(token_reader))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    Ok(())
}

#[cfg(not(unix))]
fn configure_managed_process(_command: &mut StdCommand, _token: &str) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "the learning-core process-group supervisor currently requires Unix",
    ))
}

fn terminate_child(
    child: Option<ManagedProcess>,
    termination_waiter: Option<mpsc::Receiver<()>>,
) -> bool {
    let Some(child) = child else {
        return true;
    };
    terminate_managed_process(
        child,
        termination_waiter.as_ref(),
        TERMINATION_GRACE_TIMEOUT,
        FORCE_KILL_WAIT_TIMEOUT,
    )
}

fn terminate_unmanaged_child(child: ManagedProcess) -> bool {
    terminate_managed_process(
        child,
        None,
        TERMINATION_GRACE_TIMEOUT,
        FORCE_KILL_WAIT_TIMEOUT,
    )
}

fn terminate_managed_process(
    process: ManagedProcess,
    termination_waiter: Option<&mpsc::Receiver<()>>,
    graceful_timeout: Duration,
    force_timeout: Duration,
) -> bool {
    if !managed_process_group_is_alive(process) {
        return true;
    }
    if let Err(error) = signal_managed_process_group(process, libc::SIGTERM) {
        eprintln!(
            "learning-core process-group graceful termination failed: {}",
            sanitize_log_text(&error.to_string())
        );
    }
    if wait_for_managed_process_group(process, termination_waiter, graceful_timeout) {
        return true;
    }
    if let Err(error) = signal_managed_process_group(process, libc::SIGKILL) {
        eprintln!(
            "learning-core process-group force termination failed: {}",
            sanitize_log_text(&error.to_string())
        );
    }
    wait_for_forced_process_group_exit(process, termination_waiter, force_timeout)
}

fn wait_for_forced_process_group_exit(
    process: ManagedProcess,
    termination_waiter: Option<&mpsc::Receiver<()>>,
    timeout: Duration,
) -> bool {
    let deadline = std::time::Instant::now() + timeout;
    loop {
        if !managed_process_group_is_alive(process) {
            return true;
        }
        if let Some(waiter) = termination_waiter {
            let _ = waiter.try_recv();
        }
        if std::time::Instant::now() >= deadline {
            return false;
        }
        // A stopped wrapper can lose its leader while an external command is crossing an
        // exec/reparent boundary. Reassert SIGKILL for the same validated, isolated group until
        // the kernel reports ESRCH; never release the replacement gate merely because the group
        // leader exited.
        if let Err(error) = signal_managed_process_group(process, libc::SIGKILL) {
            eprintln!(
                "learning-core process-group repeated force termination failed: {}",
                sanitize_log_text(&error.to_string())
            );
        }
        thread::sleep(Duration::from_millis(20));
    }
}

fn wait_for_managed_process_group(
    process: ManagedProcess,
    termination_waiter: Option<&mpsc::Receiver<()>>,
    timeout: Duration,
) -> bool {
    let deadline = std::time::Instant::now() + timeout;
    loop {
        if !managed_process_group_is_alive(process) {
            return true;
        }
        if let Some(waiter) = termination_waiter {
            let _ = waiter.try_recv();
        }
        if std::time::Instant::now() >= deadline {
            return false;
        }
        thread::sleep(Duration::from_millis(20));
    }
}

#[cfg(all(test, unix))]
fn managed_process_is_isolated(process: ManagedProcess) -> bool {
    if process.leader_pid <= 1 || process.leader_pid > libc::pid_t::MAX as u32 {
        return false;
    }
    // SAFETY: the PID comes from a child that was just spawned with `process_group(0)`.
    let actual_group = unsafe { libc::getpgid(process.leader_pid as libc::pid_t) };
    actual_group == process.process_group_id as libc::pid_t
        // SAFETY: `getpgrp` has no arguments and cannot violate memory safety.
        && actual_group != unsafe { libc::getpgrp() }
}

#[cfg(unix)]
fn signal_managed_process_group(process: ManagedProcess, signal: libc::c_int) -> io::Result<()> {
    if !managed_process_isolation_is_safe(process) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "refused to signal a non-isolated learning-core process group",
        ));
    }
    // SAFETY: the negative, validated process-group ID targets only the isolated sidecar tree.
    let result = unsafe { libc::kill(-(process.process_group_id as libc::pid_t), signal) };
    if result == 0 || io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH) {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

#[cfg(not(unix))]
fn signal_managed_process_group(_process: ManagedProcess, _signal: libc::c_int) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "process-group signals require Unix",
    ))
}

#[cfg(unix)]
fn managed_process_group_is_alive(process: ManagedProcess) -> bool {
    if !managed_process_isolation_is_safe(process) {
        return true;
    }
    // SAFETY: signal 0 only probes the isolated process group and does not deliver a signal.
    let result = unsafe { libc::kill(-(process.process_group_id as libc::pid_t), 0) };
    result == 0 || io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
}

#[cfg(not(unix))]
fn managed_process_group_is_alive(_process: ManagedProcess) -> bool {
    true
}

#[cfg(unix)]
fn managed_process_isolation_is_safe(process: ManagedProcess) -> bool {
    process.process_group_id > 1
        && process.process_group_id <= libc::pid_t::MAX as u32
        // SAFETY: `getpgrp` has no arguments and cannot violate memory safety.
        && process.process_group_id as libc::pid_t != unsafe { libc::getpgrp() }
}

#[cfg(not(unix))]
fn managed_process_isolation_is_safe(_process: ManagedProcess) -> bool {
    false
}

fn launch_program() -> Result<LaunchProgram, SidecarError> {
    if !cfg!(debug_assertions) {
        return Ok(LaunchProgram::Bundled);
    }

    let repository_root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let python = repository_root.join(".venv/bin/python");
    let service_root = repository_root.join("services/learning-core");
    if !python.is_file() || !service_root.is_dir() {
        return Err(SidecarError::DevelopmentRuntimeUnavailable);
    }
    Ok(LaunchProgram::Development {
        python,
        service_root,
    })
}

fn prepare_database_path(requested: &Path) -> Result<PathBuf, SidecarError> {
    let file_name = requested
        .file_name()
        .filter(|name| *name == DATABASE_FILE_NAME)
        .ok_or(SidecarError::DatabaseBoundary)?;
    let parent = requested.parent().ok_or(SidecarError::DatabaseBoundary)?;
    std::fs::create_dir_all(parent).map_err(SidecarError::DataDirectory)?;
    let canonical_parent = parent.canonicalize().map_err(SidecarError::DataDirectory)?;
    set_private_directory_permissions(&canonical_parent)?;
    let candidate = canonical_parent.join(file_name);
    let prepared = if candidate.exists() {
        canonicalize_within(&candidate, &canonical_parent)
            .map_err(|_| SidecarError::DatabaseBoundary)
    } else {
        Ok(candidate)
    }?;
    prepare_private_database_file(&prepared)?;
    Ok(prepared)
}

fn prepare_documents_path(database_path: &Path) -> Result<PathBuf, SidecarError> {
    let data_root = database_path
        .parent()
        .ok_or(SidecarError::DocumentsBoundary)?
        .canonicalize()
        .map_err(SidecarError::DataDirectory)?;
    let requested = data_root.join(DOCUMENTS_DIRECTORY_NAME);
    if !requested.exists() {
        std::fs::create_dir(&requested).map_err(SidecarError::DataDirectory)?;
    }
    let resolved =
        canonicalize_within(&requested, &data_root).map_err(|_| SidecarError::DocumentsBoundary)?;
    if !resolved.is_dir() {
        return Err(SidecarError::DocumentsBoundary);
    }
    set_private_directory_permissions(&resolved)?;
    Ok(resolved)
}

#[cfg(unix)]
fn prepare_private_database_file(path: &Path) -> Result<(), SidecarError> {
    use std::{
        fs::OpenOptions,
        os::unix::fs::{OpenOptionsExt, PermissionsExt},
    };

    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(path)
        .map_err(SidecarError::DataDirectory)?;
    let metadata = file.metadata().map_err(SidecarError::DataDirectory)?;
    if !metadata.is_file() {
        return Err(SidecarError::DatabaseBoundary);
    }
    let mut permissions = metadata.permissions();
    permissions.set_mode(0o600);
    file.set_permissions(permissions)
        .map_err(SidecarError::DataDirectory)
}

#[cfg(not(unix))]
fn prepare_private_database_file(path: &Path) -> Result<(), SidecarError> {
    std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(path)
        .map(|_| ())
        .map_err(SidecarError::DataDirectory)
}

fn prepare_temporary_path(requested: &Path) -> Result<PathBuf, SidecarError> {
    let parent = requested.parent().ok_or(SidecarError::TemporaryBoundary)?;
    std::fs::create_dir_all(parent).map_err(SidecarError::DataDirectory)?;
    let canonical_parent = parent.canonicalize().map_err(SidecarError::DataDirectory)?;
    let file_name = requested
        .file_name()
        .filter(|name| *name == SIDECAR_TEMP_DIRECTORY_NAME)
        .ok_or(SidecarError::TemporaryBoundary)?;
    let candidate = canonical_parent.join(file_name);
    if !candidate.exists() {
        std::fs::create_dir(&candidate).map_err(SidecarError::DataDirectory)?;
    }
    let resolved_root = canonicalize_within(&candidate, &canonical_parent)
        .map_err(|_| SidecarError::TemporaryBoundary)?;
    if !resolved_root.is_dir() {
        return Err(SidecarError::TemporaryBoundary);
    }
    set_private_directory_permissions(&resolved_root)?;
    cleanup_stale_temporary_generations(&resolved_root)?;

    let generation_name = format!(
        "generation-{}-{}",
        std::process::id(),
        generate_session_token()
    );
    let generation = resolved_root.join(generation_name);
    std::fs::create_dir(&generation).map_err(SidecarError::DataDirectory)?;
    set_private_directory_permissions(&generation)?;
    canonicalize_within(&generation, &resolved_root).map_err(|_| SidecarError::TemporaryBoundary)
}

fn cleanup_stale_temporary_generations(root: &Path) -> Result<(), SidecarError> {
    for entry in std::fs::read_dir(root).map_err(SidecarError::DataDirectory)? {
        let entry = entry.map_err(SidecarError::DataDirectory)?;
        let file_type = entry.file_type().map_err(SidecarError::DataDirectory)?;
        if !file_type.is_dir() || file_type.is_symlink() {
            continue;
        }
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        let Some(remainder) = name.strip_prefix("generation-") else {
            continue;
        };
        let Some((owner, _identifier)) = remainder.split_once('-') else {
            continue;
        };
        let Ok(owner_pid) = owner.parse::<u32>() else {
            continue;
        };
        if owner_pid != std::process::id() && !operating_system_process_is_alive(owner_pid) {
            std::fs::remove_dir_all(entry.path()).map_err(SidecarError::DataDirectory)?;
        }
    }
    Ok(())
}

fn remove_generation_temporary_path(path: &Path) {
    if let Err(error) = std::fs::remove_dir_all(path) {
        if error.kind() != io::ErrorKind::NotFound {
            eprintln!("learning-core temporary cleanup failed: {error}");
        }
    }
}

#[cfg(unix)]
fn operating_system_process_is_alive(pid: u32) -> bool {
    if pid <= 1 || pid > libc::pid_t::MAX as u32 {
        return false;
    }
    // SAFETY: signal 0 performs an existence/permission probe and does not signal the process.
    let result = unsafe { libc::kill(pid as libc::pid_t, 0) };
    result == 0 || io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

#[cfg(not(unix))]
fn operating_system_process_is_alive(_pid: u32) -> bool {
    true
}

#[cfg(unix)]
fn set_private_directory_permissions(path: &Path) -> Result<(), SidecarError> {
    use std::os::unix::fs::PermissionsExt;

    let mut permissions = path
        .metadata()
        .map_err(SidecarError::DataDirectory)?
        .permissions();
    permissions.set_mode(0o700);
    std::fs::set_permissions(path, permissions).map_err(SidecarError::DataDirectory)
}

#[cfg(not(unix))]
fn set_private_directory_permissions(_path: &Path) -> Result<(), SidecarError> {
    Ok(())
}

fn loopback_base_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

fn connection_view_from_state(state: &SupervisorState) -> SidecarConnectionView {
    let endpoint = (state.status == SidecarStatus::Ready)
        .then_some(state.endpoint.as_ref())
        .flatten();
    SidecarConnectionView {
        available: endpoint.is_some(),
        port: endpoint.map(|value| value.port),
        base_url: endpoint.map(|value| loopback_base_url(value.port)),
        token: endpoint.map(|value| value.token.clone()),
        status: state.status,
        phase: state.phase,
        message: state.message.clone(),
    }
}

fn prepare_manual_restart_state(
    state: &mut SupervisorState,
    reason: &str,
) -> ManualRestartPreparation {
    if state.shutting_down {
        return ManualRestartPreparation::Rejected(
            "the application is exiting; learning-core restart was refused",
        );
    }
    if matches!(
        state.status,
        SidecarStatus::Starting | SidecarStatus::Restarting
    ) || state.launch_in_progress
    {
        return ManualRestartPreparation::Idempotent(connection_view_from_state(state));
    }

    state.status = SidecarStatus::Restarting;
    state.phase = None;
    state.message = Some("Restarting the local learning service.".to_owned());
    state.last_restart_reason = Some(reason.to_owned());
    state.launch_in_progress = false;
    state.active_generation = None;
    state.endpoint = None;
    ManualRestartPreparation::Begin(ManualRestartResources {
        child: state.child.take(),
        termination_waiter: state.termination_waiter.take(),
        generation_temporary_path: state.generation_temporary_path.take(),
    })
}

fn new_session_token() -> String {
    generate_session_token()
}

fn probe_health(port: u16, token: &str) -> bool {
    let address = SocketAddr::V4(SocketAddrV4::new(Ipv4Addr::LOCALHOST, port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, HEALTH_IO_TIMEOUT) else {
        return false;
    };
    if stream.set_read_timeout(Some(HEALTH_IO_TIMEOUT)).is_err()
        || stream.set_write_timeout(Some(HEALTH_IO_TIMEOUT)).is_err()
    {
        return false;
    }
    let request = format!(
        "GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = Vec::with_capacity(2_048);
    let Ok(_) = (&mut stream).take(8_192).read_to_end(&mut response) else {
        return false;
    };
    (response.starts_with(b"HTTP/1.1 200") || response.starts_with(b"HTTP/1.0 200"))
        && response
            .windows(b"\"service\":\"keen-learning-core\"".len())
            .any(|window| window == b"\"service\":\"keen-learning-core\"")
}

fn parse_lifecycle_event(line: &[u8]) -> Option<LifecycleEvent> {
    let line = std::str::from_utf8(line).ok()?;
    let line = line
        .strip_suffix("\r\n")
        .or_else(|| line.strip_suffix('\n'))
        .unwrap_or(line);
    if line.contains(['\r', '\n']) {
        return None;
    }
    if line == READY_ANNOUNCEMENT {
        return Some(LifecycleEvent::Ready);
    }
    if let Some(port) = line.strip_prefix(PORT_ANNOUNCEMENT_PREFIX) {
        let port = port.parse::<u16>().ok()?;
        return (port > 0).then_some(LifecycleEvent::Port(port));
    }
    let phase = line.strip_prefix(PHASE_ANNOUNCEMENT_PREFIX)?;
    match phase {
        "migrating" => Some(LifecycleEvent::Phase(SidecarPhase::Migrating)),
        "recovering" => Some(LifecycleEvent::Phase(SidecarPhase::Recovering)),
        "starting_server" => Some(LifecycleEvent::Phase(SidecarPhase::StartingServer)),
        _ => None,
    }
}

fn seed_demo_requested(value: Option<&std::ffi::OsStr>) -> bool {
    value == Some(std::ffi::OsStr::new("1"))
}

fn embedding_arguments_from_environment() -> Result<Option<EmbeddingArguments>, SidecarError> {
    embedding_arguments_from_values([
        std::env::var_os(EMBEDDING_PROVIDER_ENVIRONMENT_KEY),
        std::env::var_os(EMBEDDING_BASE_URL_ENVIRONMENT_KEY),
        std::env::var_os(EMBEDDING_MODEL_ENVIRONMENT_KEY),
        std::env::var_os(EMBEDDING_VERSION_ENVIRONMENT_KEY),
        std::env::var_os(EMBEDDING_DIMENSIONS_ENVIRONMENT_KEY),
    ])
}

fn chat_arguments_from_environment() -> Result<Option<ChatArguments>, SidecarError> {
    chat_arguments_from_values([
        std::env::var_os(CHAT_PROVIDER_ENVIRONMENT_KEY),
        std::env::var_os(CHAT_BASE_URL_ENVIRONMENT_KEY),
        std::env::var_os(CHAT_MODEL_ENVIRONMENT_KEY),
        std::env::var_os(CHAT_VERSION_ENVIRONMENT_KEY),
    ])
}

fn chat_arguments_from_values(
    values: [Option<OsString>; 4],
) -> Result<Option<ChatArguments>, SidecarError> {
    if values.iter().all(Option::is_none) {
        return Ok(None);
    }
    let [provider, base_url, model, version] = values;
    let (Some(provider), Some(base_url), Some(model), Some(version)) =
        (provider, base_url, model, version)
    else {
        return Err(SidecarError::ChatConfiguration);
    };
    if validate_model_provider_arguments(&provider, &base_url, &model, &version).is_err() {
        return Err(SidecarError::ChatConfiguration);
    }
    Ok(Some(ChatArguments {
        provider,
        base_url,
        model,
        version,
    }))
}

fn embedding_arguments_from_values(
    values: [Option<OsString>; 5],
) -> Result<Option<EmbeddingArguments>, SidecarError> {
    if values.iter().all(Option::is_none) {
        return Ok(None);
    }
    let [provider, base_url, model, version, dimensions] = values;
    let (Some(provider), Some(base_url), Some(model), Some(version), Some(dimensions)) =
        (provider, base_url, model, version, dimensions)
    else {
        return Err(SidecarError::EmbeddingConfiguration);
    };
    validate_embedding_arguments(&provider, &base_url, &model, &version, &dimensions)?;
    Ok(Some(EmbeddingArguments {
        provider,
        base_url,
        model,
        version,
        dimensions,
    }))
}

fn validate_embedding_arguments(
    provider: &std::ffi::OsStr,
    base_url: &std::ffi::OsStr,
    model: &std::ffi::OsStr,
    version: &std::ffi::OsStr,
    dimensions: &std::ffi::OsStr,
) -> Result<(), SidecarError> {
    validate_model_provider_arguments(provider, base_url, model, version)?;
    let dimensions = dimensions
        .to_str()
        .ok_or(SidecarError::EmbeddingConfiguration)?;
    let valid_dimensions = matches!(
        dimensions.parse::<u16>(),
        Ok(value) if (1..=8_192).contains(&value)
    );
    if !valid_dimensions {
        return Err(SidecarError::EmbeddingConfiguration);
    }
    Ok(())
}

fn validate_model_provider_arguments(
    provider: &std::ffi::OsStr,
    base_url: &std::ffi::OsStr,
    model: &std::ffi::OsStr,
    version: &std::ffi::OsStr,
) -> Result<(), SidecarError> {
    let provider = provider
        .to_str()
        .ok_or(SidecarError::EmbeddingConfiguration)?;
    let base_url = base_url
        .to_str()
        .ok_or(SidecarError::EmbeddingConfiguration)?;
    let model = model.to_str().ok_or(SidecarError::EmbeddingConfiguration)?;
    let version = version
        .to_str()
        .ok_or(SidecarError::EmbeddingConfiguration)?;
    if !matches!(provider, "ollama" | "openai-compatible")
        || !valid_embedding_identity(model)
        || !valid_embedding_identity(version)
        || !valid_loopback_provider_url(base_url)
    {
        return Err(SidecarError::EmbeddingConfiguration);
    }
    Ok(())
}

fn valid_embedding_identity(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 256 && !value.chars().any(char::is_control)
}

fn valid_loopback_provider_url(value: &str) -> bool {
    if value.contains(['\\', '#']) || value.chars().any(char::is_whitespace) {
        return false;
    }
    let Some(remainder) = value.strip_prefix("http://") else {
        return false;
    };
    let authority_end = remainder.find(['/', '?']).unwrap_or(remainder.len());
    let authority = &remainder[..authority_end];
    if authority.contains('@') || authority.contains('%') {
        return false;
    }
    authority
        .parse::<std::net::SocketAddr>()
        .ok()
        .is_some_and(|address| address.ip().is_loopback() && address.port() > 0)
}

fn normalized_restart_reason(reason: Option<&str>) -> &'static str {
    match reason {
        Some("health_check_failed") => "authenticated health check failed",
        Some("sidecar_unavailable") => "learning service unavailable",
        Some("configuration_recovered") => "configuration was repaired",
        _ => "user requested retry",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Barrier,
    };

    #[cfg(unix)]
    struct ManagedProcessTestGuard(Option<ManagedProcess>);

    #[cfg(unix)]
    impl Drop for ManagedProcessTestGuard {
        fn drop(&mut self) {
            if let Some(process) = self.0.take() {
                let _ = signal_managed_process_group(process, libc::SIGKILL);
                let _ = wait_for_managed_process_group(process, None, Duration::from_secs(2));
            }
        }
    }

    #[test]
    fn accepts_only_exact_lifecycle_announcements() {
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_PORT=43125"),
            Some(LifecycleEvent::Port(43125))
        );
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_PORT=43125\n"),
            Some(LifecycleEvent::Port(43125))
        );
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_PORT=43125\r\n"),
            Some(LifecycleEvent::Port(43125))
        );
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_PHASE=migrating\n"),
            Some(LifecycleEvent::Phase(SidecarPhase::Migrating))
        );
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_PHASE=recovering\n"),
            Some(LifecycleEvent::Phase(SidecarPhase::Recovering))
        );
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_PHASE=starting_server\n"),
            Some(LifecycleEvent::Phase(SidecarPhase::StartingServer))
        );
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_READY=1\n"),
            Some(LifecycleEvent::Ready)
        );
        assert_eq!(parse_lifecycle_event(b"KEEN_SIDECAR_PORT=0"), None);
        assert_eq!(parse_lifecycle_event(b"KEEN_SIDECAR_PORT=65536"), None);
        assert_eq!(parse_lifecycle_event(b"log KEEN_SIDECAR_PORT=43125"), None);
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_PORT=43125 extra"),
            None
        );
        assert_eq!(parse_lifecycle_event(b"KEEN_SIDECAR_PORT=43125 \n"), None);
        assert_eq!(parse_lifecycle_event(b"log KEEN_SIDECAR_READY=1\n"), None);
        assert_eq!(parse_lifecycle_event(b"KEEN_SIDECAR_READY=1 \n"), None);
        assert_eq!(
            parse_lifecycle_event(b"KEEN_SIDECAR_READY=1\nignored\n"),
            None
        );
    }

    #[test]
    fn demo_seed_requires_the_exact_opt_in_value() {
        assert!(!seed_demo_requested(None));
        assert!(!seed_demo_requested(Some(std::ffi::OsStr::new(""))));
        assert!(!seed_demo_requested(Some(std::ffi::OsStr::new("0"))));
        assert!(!seed_demo_requested(Some(std::ffi::OsStr::new("true"))));
        assert!(seed_demo_requested(Some(std::ffi::OsStr::new("1"))));

        let arguments = SidecarArguments {
            database_path: PathBuf::from("/tmp/Keen Data/learning-core.sqlite3"),
            documents_path: PathBuf::from("/tmp/Keen Data/documents"),
            seed_demo: false,
            embedding: None,
            chat: None,
        }
        .into_os_strings();
        assert!(!arguments.iter().any(|argument| argument == "--seed-demo"));
    }

    #[test]
    fn startup_timeouts_are_independent_and_allow_slow_migrations() {
        assert_eq!(PORT_ANNOUNCEMENT_TIMEOUT, Duration::from_secs(10));
        assert_eq!(READY_ANNOUNCEMENT_TIMEOUT, Duration::from_secs(90));
        assert_eq!(HEALTH_CONFIRMATION_TIMEOUT, Duration::from_secs(10));
        assert!(READY_ANNOUNCEMENT_TIMEOUT > Duration::from_secs(6));
        assert_ne!(PORT_ANNOUNCEMENT_TIMEOUT, READY_ANNOUNCEMENT_TIMEOUT);
        assert_ne!(READY_ANNOUNCEMENT_TIMEOUT, HEALTH_CONFIRMATION_TIMEOUT);
    }

    #[test]
    fn embedding_arguments_are_all_or_none_and_forwarded_as_fixed_values() {
        assert!(
            embedding_arguments_from_values([None, None, None, None, None])
                .expect("absent configuration")
                .is_none()
        );
        assert!(matches!(
            embedding_arguments_from_values([
                Some(OsString::from("ollama")),
                None,
                None,
                None,
                None,
            ]),
            Err(SidecarError::EmbeddingConfiguration)
        ));
        for invalid_values in [
            ["cloud", "http://127.0.0.1:11434", "model", "v1", "3"],
            ["ollama", "https://127.0.0.1:11434", "model", "v1", "3"],
            ["ollama", "http://example.com:11434", "model", "v1", "3"],
            ["ollama", "http://127.0.0.1:11434", "model", "v1", "0"],
            ["ollama", "http://127.0.0.1:11434", "model\n", "v1", "3"],
        ] {
            assert!(matches!(
                embedding_arguments_from_values(invalid_values.map(OsString::from).map(Some)),
                Err(SidecarError::EmbeddingConfiguration)
            ));
        }

        let embedding = embedding_arguments_from_values([
            Some(OsString::from("ollama")),
            Some(OsString::from("http://127.0.0.1:11434")),
            Some(OsString::from("nomic-embed-text")),
            Some(OsString::from("v1")),
            Some(OsString::from("768")),
        ])
        .expect("complete configuration");
        let arguments = SidecarArguments {
            database_path: PathBuf::from("/tmp/keen.sqlite3"),
            documents_path: PathBuf::from("/tmp/documents"),
            seed_demo: false,
            embedding,
            chat: None,
        }
        .into_os_strings();

        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--embedding-provider", "ollama"]));
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--embedding-base-url", "http://127.0.0.1:11434"]));
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--embedding-model", "nomic-embed-text"]));
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--embedding-version", "v1"]));
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--embedding-dimensions", "768"]));
    }

    #[test]
    fn chat_arguments_are_all_or_none_loopback_only_and_forwarded() {
        assert!(chat_arguments_from_values([None, None, None, None])
            .expect("absent chat configuration")
            .is_none());
        assert!(matches!(
            chat_arguments_from_values([
                Some(OsString::from("ollama")),
                Some(OsString::from("http://127.0.0.1:11434")),
                None,
                Some(OsString::from("v1")),
            ]),
            Err(SidecarError::ChatConfiguration)
        ));
        assert!(matches!(
            chat_arguments_from_values([
                Some(OsString::from("ollama")),
                Some(OsString::from("http://example.com:11434")),
                Some(OsString::from("local-chat")),
                Some(OsString::from("v1")),
            ]),
            Err(SidecarError::ChatConfiguration)
        ));
        let chat = chat_arguments_from_values([
            Some(OsString::from("openai-compatible")),
            Some(OsString::from("http://127.0.0.1:1234/v1")),
            Some(OsString::from("local-chat")),
            Some(OsString::from("sha256:fixture")),
        ])
        .expect("complete chat configuration");
        let arguments = SidecarArguments {
            database_path: PathBuf::from("/tmp/keen.sqlite3"),
            documents_path: PathBuf::from("/tmp/documents"),
            seed_demo: false,
            embedding: None,
            chat,
        }
        .into_os_strings();
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--chat-provider", "openai-compatible"]));
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--chat-base-url", "http://127.0.0.1:1234/v1"]));
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--chat-model", "local-chat"]));
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--chat-version", "sha256:fixture"]));
    }

    #[test]
    fn public_status_and_phase_values_match_the_frontend_contract() {
        assert_eq!(
            serde_json::to_value(SidecarStatus::ConfigurationError).expect("status JSON"),
            "configuration_error"
        );
        assert_eq!(
            serde_json::to_value(SidecarPhase::StartingServer).expect("phase JSON"),
            "starting_server"
        );
        assert_eq!(
            serde_json::to_value(SidecarPhase::HealthChecking).expect("phase JSON"),
            "health_checking"
        );
    }

    #[test]
    fn a_new_generation_never_reuses_the_old_token_even_on_the_same_port() {
        let old = Endpoint {
            port: 43125,
            token: new_session_token(),
        };
        let new = Endpoint {
            port: old.port,
            token: new_session_token(),
        };
        assert_eq!(old.port, new.port);
        assert_ne!(old.token, new.token);
    }

    #[test]
    fn concurrent_manual_restart_preparation_claims_one_generation() {
        let root = tempfile::tempdir().expect("sidecar supervisor root");
        let supervisor = SidecarSupervisor::new(
            root.path().join(DATABASE_FILE_NAME),
            root.path().join("cache"),
        );
        {
            let mut state = supervisor.lock();
            state.status = SidecarStatus::Unavailable;
        }
        let barrier = Arc::new(Barrier::new(3));
        let begin_count = Arc::new(AtomicUsize::new(0));
        let mut workers = Vec::new();
        for _ in 0..2 {
            let supervisor = supervisor.clone();
            let barrier = barrier.clone();
            let begin_count = begin_count.clone();
            workers.push(thread::spawn(move || {
                barrier.wait();
                let _lifecycle = supervisor.lock_lifecycle();
                let preparation = {
                    let mut state = supervisor.lock();
                    prepare_manual_restart_state(&mut state, "user requested retry")
                };
                if matches!(preparation, ManualRestartPreparation::Begin(_)) {
                    begin_count.fetch_add(1, Ordering::SeqCst);
                }
            }));
        }
        barrier.wait();
        for worker in workers {
            worker.join().expect("manual restart worker");
        }
        assert_eq!(begin_count.load(Ordering::SeqCst), 1);
        assert_eq!(supervisor.lock().status, SidecarStatus::Restarting);
    }

    #[test]
    fn manual_restart_is_rejected_after_shutdown_begins() {
        let mut state = SupervisorState {
            status: SidecarStatus::Unavailable,
            shutting_down: true,
            ..SupervisorState::default()
        };
        assert!(matches!(
            prepare_manual_restart_state(&mut state, "user requested retry"),
            ManualRestartPreparation::Rejected(_)
        ));
        assert!(!state.launch_in_progress);
        assert_eq!(state.status, SidecarStatus::Unavailable);
    }

    #[test]
    fn manual_restart_from_ready_invalidates_the_old_generation() {
        let mut state = SupervisorState {
            status: SidecarStatus::Ready,
            active_generation: Some(9),
            endpoint: Some(Endpoint {
                port: 43125,
                token: "old-generation-token".to_owned(),
            }),
            ..SupervisorState::default()
        };

        assert!(matches!(
            prepare_manual_restart_state(&mut state, "user requested retry"),
            ManualRestartPreparation::Begin(_)
        ));
        assert_eq!(state.status, SidecarStatus::Restarting);
        assert_eq!(state.active_generation, None);
        assert!(state.endpoint.is_none());
        assert!(!state.launch_in_progress);
        assert_eq!(
            state.last_restart_reason.as_deref(),
            Some("user requested retry")
        );
    }

    #[test]
    fn shutdown_intent_blocks_launch_while_shutdown_waits_for_the_lifecycle_gate() {
        let root = tempfile::tempdir().expect("sidecar supervisor root");
        let supervisor = SidecarSupervisor::new(
            root.path().join(DATABASE_FILE_NAME),
            root.path().join("cache"),
        );
        {
            let mut state = supervisor.lock();
            state.status = SidecarStatus::Restarting;
            state.launch_in_progress = true;
        }

        let (gate_held_sender, gate_held_receiver) = mpsc::sync_channel(1);
        let (release_sender, release_receiver) = mpsc::sync_channel(1);
        let gate_supervisor = supervisor.clone();
        let gate_holder = thread::spawn(move || {
            let _lifecycle = gate_supervisor.lock_lifecycle();
            gate_held_sender.send(()).expect("gate held signal");
            release_receiver.recv().expect("release gate signal");
        });
        gate_held_receiver
            .recv_timeout(Duration::from_secs(1))
            .expect("lifecycle gate held");

        let shutdown_supervisor = supervisor.clone();
        let shutdown = thread::spawn(move || shutdown_supervisor.shutdown());
        let deadline = std::time::Instant::now() + Duration::from_secs(1);
        while !supervisor.shutdown_is_requested() && std::time::Instant::now() < deadline {
            thread::yield_now();
        }

        assert!(supervisor.shutdown_is_requested());
        assert!(!supervisor.lock().shutting_down);
        assert!(!supervisor.should_continue_launch());

        release_sender.send(()).expect("release lifecycle gate");
        gate_holder.join().expect("lifecycle gate holder");
        shutdown.join().expect("shutdown worker");
        let state = supervisor.lock();
        assert!(state.shutting_down);
        assert_eq!(state.status, SidecarStatus::Stopped);
        assert!(!state.launch_in_progress);
    }

    #[test]
    fn process_output_reader_rejects_an_oversized_single_frame() {
        let oversized = vec![b'x'; MAX_PROCESS_OUTPUT_LINE_BYTES + 1];
        let (sender, receiver) = mpsc::channel();
        let reader = spawn_process_output_reader(
            io::Cursor::new(oversized),
            sender,
            ManagedProcessEvent::Stdout,
            "stdout",
        );
        match receiver
            .recv_timeout(Duration::from_secs(1))
            .expect("output limit event")
        {
            ManagedProcessEvent::Error(message) => {
                assert!(message.contains("stdout line exceeded"));
                assert!(message.contains(&MAX_PROCESS_OUTPUT_LINE_BYTES.to_string()));
            }
            event => panic!("expected output limit error, received {event:?}"),
        }
        reader.join().expect("output reader");
    }

    #[test]
    fn process_output_reader_accepts_a_frame_at_the_byte_limit() {
        let mut bounded = vec![b'x'; MAX_PROCESS_OUTPUT_LINE_BYTES - 1];
        bounded.push(b'\n');
        let (sender, receiver) = mpsc::channel();
        let reader = spawn_process_output_reader(
            io::Cursor::new(bounded),
            sender,
            ManagedProcessEvent::Stdout,
            "stdout",
        );
        match receiver
            .recv_timeout(Duration::from_secs(1))
            .expect("bounded output event")
        {
            ManagedProcessEvent::Stdout(line) => {
                assert_eq!(line.len(), MAX_PROCESS_OUTPUT_LINE_BYTES);
                assert_eq!(line.last(), Some(&b'\n'));
            }
            event => panic!("expected bounded stdout frame, received {event:?}"),
        }
        reader.join().expect("output reader");
    }

    #[test]
    fn sanitized_logs_always_fit_on_one_physical_line() {
        let sanitized = sanitize_log_text("first\r\nsecond\tfield\u{0007}");
        assert_eq!(sanitized, "first\\r\\nsecond\\tfield�");
        assert!(!sanitized.contains('\r'));
        assert!(!sanitized.contains('\n'));
        assert!(!sanitized.contains('\t'));
    }

    #[cfg(unix)]
    #[test]
    fn lifecycle_gate_blocks_launch_until_the_old_process_group_exits() {
        let root = tempfile::tempdir().expect("sidecar supervisor root");
        let supervisor = SidecarSupervisor::new(
            root.path().join(DATABASE_FILE_NAME),
            root.path().join("cache"),
        );
        let mut command = StdCommand::new("/bin/sh");
        command.args(["-c", "trap '' TERM; while :; do sleep 60; done"]);
        let (_receiver, process) =
            spawn_managed_process(command, "test-token").expect("managed process");
        assert!(managed_process_group_is_alive(process));

        let gate_acquired = Arc::new(Barrier::new(2));
        let launched = Arc::new(AtomicBool::new(false));
        let teardown_supervisor = supervisor.clone();
        let teardown_barrier = gate_acquired.clone();
        let teardown = thread::spawn(move || {
            let _lifecycle = teardown_supervisor.lock_lifecycle();
            teardown_barrier.wait();
            thread::sleep(Duration::from_millis(80));
            assert!(terminate_managed_process(
                process,
                None,
                Duration::ZERO,
                Duration::from_secs(2),
            ));
        });
        gate_acquired.wait();

        let launch_supervisor = supervisor.clone();
        let launch_observed = launched.clone();
        let launch = thread::spawn(move || {
            let _lifecycle = launch_supervisor.lock_lifecycle();
            launch_observed.store(true, Ordering::SeqCst);
        });
        thread::sleep(Duration::from_millis(30));
        assert!(!launched.load(Ordering::SeqCst));
        assert!(managed_process_group_is_alive(process));

        teardown.join().expect("old process teardown");
        launch.join().expect("new generation launch gate");
        assert!(!managed_process_group_is_alive(process));
        assert!(launched.load(Ordering::SeqCst));
    }

    #[test]
    fn lifecycle_state_is_ordered_and_generation_isolated() {
        let root = tempfile::tempdir().expect("sidecar supervisor root");
        let supervisor = SidecarSupervisor::new(
            root.path().join(DATABASE_FILE_NAME),
            root.path().join("cache"),
        );
        {
            let mut state = supervisor.lock();
            state.status = SidecarStatus::Starting;
            state.phase = Some(SidecarPhase::Binding);
            state.active_generation = Some(7);
        }

        assert!(!supervisor.register_phase(7, SidecarPhase::Migrating));
        assert!(!supervisor.register_endpoint(
            6,
            Endpoint {
                port: 43125,
                token: "old-token".to_owned(),
            }
        ));
        assert!(supervisor.register_endpoint(
            7,
            Endpoint {
                port: 43125,
                token: "current-token".to_owned(),
            }
        ));
        assert!(!supervisor.register_phase(7, SidecarPhase::Recovering));
        assert!(supervisor.register_phase(7, SidecarPhase::Migrating));
        assert!(supervisor.register_phase(7, SidecarPhase::Recovering));
        assert!(supervisor.register_phase(7, SidecarPhase::StartingServer));
        assert!(!supervisor.register_ready_signal(6));
        assert!(supervisor.register_ready_signal(7));
        supervisor.mark_ready(6);
        assert_eq!(supervisor.connection_view().status, SidecarStatus::Starting);
        supervisor.mark_ready(7);
        let view = supervisor.connection_view();
        assert_eq!(view.status, SidecarStatus::Ready);
        assert_eq!(view.port, Some(43125));
        assert_eq!(view.token.as_deref(), Some("current-token"));
    }

    #[test]
    fn shutdown_rejects_ready_from_the_active_generation() {
        let root = tempfile::tempdir().expect("sidecar supervisor root");
        let supervisor = SidecarSupervisor::new(
            root.path().join(DATABASE_FILE_NAME),
            root.path().join("cache"),
        );
        {
            let mut state = supervisor.lock();
            state.status = SidecarStatus::Starting;
            state.phase = Some(SidecarPhase::StartingServer);
            state.active_generation = Some(1);
            state.endpoint = Some(Endpoint {
                port: 43125,
                token: "current-token".to_owned(),
            });
            state.shutting_down = true;
        }
        assert!(!supervisor.register_ready_signal(1));
        supervisor.mark_ready(1);
        assert_eq!(supervisor.connection_view().status, SidecarStatus::Starting);
    }

    #[test]
    fn base_url_never_uses_a_wildcard_address() {
        let base_url = loopback_base_url(43125);
        assert_eq!(base_url, "http://127.0.0.1:43125");
        assert!(!base_url.contains("0.0.0.0"));
    }

    #[test]
    fn command_arguments_are_fixed_and_preserve_paths_with_spaces() {
        let arguments = SidecarArguments {
            database_path: PathBuf::from("/tmp/Keen Data/learning-core.sqlite3"),
            documents_path: PathBuf::from("/tmp/Keen Data/documents"),
            seed_demo: true,
            embedding: None,
            chat: None,
        }
        .into_os_strings();
        assert_eq!(
            arguments,
            vec![
                "--token-stdin",
                "--port",
                "0",
                "--database",
                "/tmp/Keen Data/learning-core.sqlite3",
                "--documents-directory",
                "/tmp/Keen Data/documents",
                "--seed-demo",
            ]
            .into_iter()
            .map(OsString::from)
            .collect::<Vec<_>>()
        );
        assert_eq!(arguments[0], "--token-stdin");
        assert!(!arguments.iter().any(|argument| argument == "--token"));
    }

    #[cfg(unix)]
    #[test]
    fn managed_process_group_kills_a_stopped_descendant_after_its_leader_dies() {
        let mut command = StdCommand::new("/bin/sh");
        command.args([
            "-c",
            "(trap '' HUP TERM; echo READY; while :; do sleep 60; done) & descendant=$!; echo PID:$descendant; wait",
        ]);
        let (receiver, process) =
            spawn_managed_process(command, "test-token").expect("managed process");
        let mut guard = ManagedProcessTestGuard(Some(process));

        assert!(managed_process_is_isolated(process));
        let mut descendant_pid = None;
        let mut descendant_ready = false;
        while descendant_pid.is_none() || !descendant_ready {
            match receiver
                .recv_timeout(Duration::from_secs(2))
                .expect("descendant PID event")
            {
                ManagedProcessEvent::Stdout(line) => {
                    let line = String::from_utf8(line).expect("UTF-8 descendant PID");
                    let line = line.trim();
                    if line == "READY" {
                        descendant_ready = true;
                    } else if let Some(pid) = line.strip_prefix("PID:") {
                        descendant_pid = Some(pid.parse::<u32>().expect("numeric descendant PID"));
                    }
                }
                ManagedProcessEvent::Error(error) => panic!("managed process error: {error}"),
                ManagedProcessEvent::Stderr(_) => {}
                ManagedProcessEvent::Terminated { code, signal } => {
                    panic!("managed process exited early: code={code:?} signal={signal:?}")
                }
            }
        }
        let descendant_pid = descendant_pid.expect("descendant PID");
        // SAFETY: the PID was emitted by the isolated test child immediately after spawning it.
        assert_eq!(
            unsafe { libc::getpgid(descendant_pid as libc::pid_t) },
            process.process_group_id as libc::pid_t
        );
        // SAFETY: both PIDs belong to this test's isolated process tree.
        assert_eq!(
            unsafe { libc::kill(descendant_pid as libc::pid_t, libc::SIGSTOP) },
            0
        );
        // Kill only the group leader, reproducing a PyInstaller bootloader crash while the
        // inner interpreter cannot run its watchdog thread.
        assert_eq!(
            unsafe { libc::kill(process.leader_pid as libc::pid_t, libc::SIGKILL) },
            0
        );

        loop {
            match receiver
                .recv_timeout(Duration::from_secs(2))
                .expect("leader termination event")
            {
                ManagedProcessEvent::Terminated { .. } => break,
                ManagedProcessEvent::Error(error) => panic!("managed process error: {error}"),
                ManagedProcessEvent::Stdout(_) | ManagedProcessEvent::Stderr(_) => {}
            }
        }
        assert!(managed_process_group_is_alive(process));
        assert!(terminate_managed_process(
            process,
            None,
            Duration::ZERO,
            Duration::from_secs(2),
        ));
        assert!(!managed_process_group_is_alive(process));
        guard.0 = None;
    }

    #[test]
    fn restart_policy_allows_only_one_restart() {
        let mut policy = RestartPolicy::new(1);
        assert_eq!(policy.after_failure(false), FailureAction::Restart);
        assert_eq!(policy.after_failure(false), FailureAction::Unavailable);
    }

    #[test]
    fn restart_policy_never_restarts_during_shutdown() {
        let mut policy = RestartPolicy::new(1);
        assert_eq!(policy.after_failure(true), FailureAction::Stop);
        assert_eq!(policy.used, 0);
    }

    #[test]
    fn shutdown_removes_its_generation_temporary_path_synchronously() {
        let root = tempfile::tempdir().expect("sidecar supervisor root");
        let database = root.path().join(DATABASE_FILE_NAME);
        std::fs::write(&database, b"persistent job fixture").expect("persistent database fixture");
        let generation = root.path().join("generation-under-test");
        std::fs::create_dir(&generation).expect("generation temporary directory");
        std::fs::write(generation.join("payload"), b"temporary payload")
            .expect("generation temporary payload");
        let supervisor = SidecarSupervisor::new(database.clone(), root.path().join("cache"));
        {
            let mut state = supervisor.lock();
            state.active_generation = Some(1);
            state.generation_temporary_path = Some(generation.clone());
        }

        supervisor.shutdown();
        // Tauri may emit ExitRequested followed by Exit; teardown must be idempotent.
        supervisor.shutdown();

        assert!(!generation.exists());
        let state = supervisor.lock();
        assert!(state.shutting_down);
        assert_eq!(state.status, SidecarStatus::Stopped);
        assert!(state.generation_temporary_path.is_none());
        assert_eq!(
            std::fs::read(database).expect("persistent database remains"),
            b"persistent job fixture"
        );
    }

    #[test]
    fn database_path_is_confined_to_its_fixed_data_directory() {
        let root = tempfile::tempdir().expect("application data directory");
        let requested = root.path().join(DATABASE_FILE_NAME);
        let prepared = prepare_database_path(&requested).expect("database path");
        assert!(prepared.starts_with(root.path().canonicalize().expect("canonical root")));
        assert_eq!(prepared.file_name().expect("file name"), DATABASE_FILE_NAME);
    }

    #[test]
    fn database_path_rejects_an_unexpected_file_name() {
        let root = tempfile::tempdir().expect("application data directory");
        let requested = root.path().join("../outside.sqlite3");
        assert!(matches!(
            prepare_database_path(&requested),
            Err(SidecarError::DatabaseBoundary)
        ));
    }

    #[test]
    fn documents_path_is_created_inside_the_application_data_directory() {
        let root = tempfile::tempdir().expect("application data directory");
        let database =
            prepare_database_path(&root.path().join(DATABASE_FILE_NAME)).expect("database path");
        let documents = prepare_documents_path(&database).expect("documents path");
        assert_eq!(
            documents,
            root.path()
                .canonicalize()
                .expect("canonical application data directory")
                .join(DOCUMENTS_DIRECTORY_NAME)
        );
        assert!(documents.is_dir());
    }

    #[cfg(unix)]
    #[test]
    fn data_paths_restrict_existing_database_and_directory_permissions() {
        use std::os::unix::fs::PermissionsExt;

        let root = tempfile::tempdir().expect("application data directory");
        std::fs::set_permissions(root.path(), std::fs::Permissions::from_mode(0o755))
            .expect("relaxed data permissions");
        let requested = root.path().join(DATABASE_FILE_NAME);
        std::fs::write(&requested, b"existing database bytes").expect("existing database");
        std::fs::set_permissions(&requested, std::fs::Permissions::from_mode(0o644))
            .expect("relaxed database permissions");
        let requested_documents = root.path().join(DOCUMENTS_DIRECTORY_NAME);
        std::fs::create_dir(&requested_documents).expect("existing documents directory");
        std::fs::set_permissions(&requested_documents, std::fs::Permissions::from_mode(0o755))
            .expect("relaxed documents permissions");

        let database = prepare_database_path(&requested).expect("private database path");
        let documents = prepare_documents_path(&database).expect("private documents path");

        assert_eq!(
            root.path()
                .metadata()
                .expect("data root metadata")
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        assert_eq!(
            database
                .metadata()
                .expect("database metadata")
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
        assert_eq!(
            documents
                .metadata()
                .expect("documents metadata")
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        assert_eq!(
            std::fs::read(database).expect("preserved database bytes"),
            b"existing database bytes"
        );
    }

    #[cfg(unix)]
    #[test]
    fn temporary_path_is_confined_and_private() {
        use std::os::unix::fs::PermissionsExt;

        let cache = tempfile::tempdir().expect("application cache directory");
        let temporary = prepare_temporary_path(&cache.path().join(SIDECAR_TEMP_DIRECTORY_NAME))
            .expect("sidecar temporary path");
        let expected_root = cache
            .path()
            .canonicalize()
            .expect("canonical application cache directory")
            .join(SIDECAR_TEMP_DIRECTORY_NAME);
        assert_eq!(temporary.parent(), Some(expected_root.as_path()));
        assert_eq!(
            expected_root
                .metadata()
                .expect("temporary root metadata")
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        assert!(temporary
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.starts_with(&format!("generation-{}-", std::process::id()))));
        assert_eq!(
            temporary
                .metadata()
                .expect("temporary path metadata")
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
    }

    #[test]
    fn temporary_path_removes_only_stale_owned_generations() {
        let cache = tempfile::tempdir().expect("application cache directory");
        let requested = cache.path().join(SIDECAR_TEMP_DIRECTORY_NAME);
        let current = prepare_temporary_path(&requested).expect("current generation");
        let root = current.parent().expect("temporary root");
        let stale = root.join("generation-2147483646-stale");
        let unrelated = root.join("unrelated-cache");
        std::fs::create_dir(&stale).expect("stale generation");
        std::fs::create_dir(&unrelated).expect("unrelated cache");

        let next = prepare_temporary_path(&requested).expect("next generation");

        assert!(!stale.exists());
        assert!(current.exists());
        assert!(next.exists());
        assert!(unrelated.exists());
    }

    #[cfg(unix)]
    #[test]
    fn database_path_rejects_a_symlink_outside_the_data_directory() {
        use std::os::unix::fs::symlink;

        let root = tempfile::tempdir().expect("application data directory");
        let outside = tempfile::NamedTempFile::new().expect("outside database");
        let requested = root.path().join(DATABASE_FILE_NAME);
        symlink(outside.path(), &requested).expect("database symlink");
        assert!(matches!(
            prepare_database_path(&requested),
            Err(SidecarError::DatabaseBoundary)
        ));
    }

    #[cfg(unix)]
    #[test]
    fn documents_path_rejects_a_symlink_outside_the_data_directory() {
        use std::os::unix::fs::symlink;

        let root = tempfile::tempdir().expect("application data directory");
        let outside = tempfile::tempdir().expect("outside documents directory");
        let database =
            prepare_database_path(&root.path().join(DATABASE_FILE_NAME)).expect("database path");
        symlink(outside.path(), root.path().join(DOCUMENTS_DIRECTORY_NAME))
            .expect("documents symlink");
        assert!(matches!(
            prepare_documents_path(&database),
            Err(SidecarError::DocumentsBoundary)
        ));
    }

    #[cfg(unix)]
    #[test]
    fn temporary_path_rejects_a_symlink_outside_the_cache_directory() {
        use std::os::unix::fs::symlink;

        let cache = tempfile::tempdir().expect("application cache directory");
        let outside = tempfile::tempdir().expect("outside temporary directory");
        let requested = cache.path().join(SIDECAR_TEMP_DIRECTORY_NAME);
        symlink(outside.path(), &requested).expect("temporary path symlink");
        assert!(matches!(
            prepare_temporary_path(&requested),
            Err(SidecarError::TemporaryBoundary)
        ));
    }
}
