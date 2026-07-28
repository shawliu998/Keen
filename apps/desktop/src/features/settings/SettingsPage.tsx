import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ChevronRight,
  FileText,
  HardDrive,
  Link2,
  RotateCcw,
  Shield,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Badge, Button, Input, Select } from "@keen/ui";
import { isLearningCoreStarting, useLearningCore, type LearningCoreStatus } from "../../services/LearningCoreProvider";
import {
  canConfigureProvider,
  getProviderConfiguration,
  providerRequiresRemoteApiKey,
  savedApiKeyAppliesToDraft,
  saveProviderConfiguration,
  type ProviderConfiguration,
} from "./providerConfiguration";
import {
  matchProviderPreset,
  providerMaturityLabel,
  providerPreset,
  providerPresets,
  type ProviderPresetId,
} from "./providerCatalog";
import {
  providerSaveFailure,
  providerTestFailure,
} from "./providerRecoveryMessages";
import { parseDeepLearnReturnTo } from "./providerRecoveryRouting";
import "./settings.css";

const sections = [
  ["Status", HardDrive],
  ["Model", Link2],
  ["Privacy", Shield],
  ["About", FileText],
] as const;

type SettingsSection = (typeof sections)[number][0];

const sectionDescriptions: Record<SettingsSection, string> = {
  Status: "Check whether Keen is ready for local learning.",
  Model: "Choose and verify the model Keen uses while you learn.",
  Privacy: "See where your learning data and provider credentials stay.",
  About: "Review Keen's core open-source software and notices.",
};

function settingsSection(value: string | null): SettingsSection {
  if (value === "capabilities") return "Model";
  if (value === "privacy") return "Privacy";
  if (value === "open-source") return "About";
  return "Status";
}

function settingsSectionParam(section: SettingsSection) {
  if (section === "Model") return "capabilities";
  if (section === "Privacy") return "privacy";
  if (section === "About") return "open-source";
  return null;
}

function detailTitle(section: SettingsSection) {
  return section === "Status" ? "Workspace status" : section;
}
type ProviderOperation = "save" | "test" | null;
type ProviderNotice = { kind: "status" | "error"; text: string } | null;

const notices = [
  "React · MIT",
  "Tauri · Apache-2.0 / MIT",
  "Lucide · ISC",
  "Zustand · MIT",
  "TanStack Query · MIT",
] as const;

function learningCoreState(status: LearningCoreStatus) {
  if (status === "demo") return {
    label: "Browser Demo",
    tone: "warning" as const,
    detail: "This browser preview uses bundled sample state and does not contact the desktop learning core.",
  };
  if (status === "healthy") return {
    label: "Available locally",
    tone: "success" as const,
    detail: "The authenticated learning core is responding on this Mac.",
  };
  if (isLearningCoreStarting(status)) return {
    label: "Starting",
    tone: "warning" as const,
    detail: "Keen is checking the supervised local service. Features that require it are not ready yet.",
  };
  return {
    label: status === "configuration_error" ? "Configuration error" : "Unavailable",
    tone: "danger" as const,
    detail: "Keen cannot currently confirm a healthy local learning core. No connected state is assumed.",
  };
}

export function SettingsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const section = settingsSection(searchParams.get("section"));
  const showingOverview = searchParams.get("section") === null;
  const learningReturn = parseDeepLearnReturnTo(searchParams.get("return_to"));
  const core = useLearningCore();
  const runtime = learningCoreState(core.status);
  const canRetry = core.status !== "demo" && core.status !== "healthy" && !isLearningCoreStarting(core.status);
  const [provider, setProvider] = useState<"ollama" | "openai-compatible">("ollama");
  const [providerPresetId, setProviderPresetId] = useState<ProviderPresetId>("ollama");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:11434");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [savedProvider, setSavedProvider] = useState<ProviderConfiguration | null>(null);
  const [providerLoadState, setProviderLoadState] = useState<"loading" | "ready" | "error">(
    canConfigureProvider() ? "loading" : "ready",
  );
  const [providerLoadAttempt, setProviderLoadAttempt] = useState(0);
  const [providerNotice, setProviderNotice] = useState<ProviderNotice>(null);
  const [providerOperation, setProviderOperation] = useState<ProviderOperation>(null);
  const [draftDirty, setDraftDirty] = useState(false);
  const [restartBaselineGeneration, setRestartBaselineGeneration] = useState<number | null>(null);
  const [restartStatusBeforeSave, setRestartStatusBeforeSave] = useState<LearningCoreStatus | null>(null);
  const [restartFailed, setRestartFailed] = useState(false);
  const [validatedGeneration, setValidatedGeneration] = useState<number | null>(null);
  const [verificationRequested, setVerificationRequested] = useState(false);
  const verificationRunGeneration = useRef<number | null>(null);
  const selectedPreset = providerPreset(providerPresetId);
  const providerBusy = providerOperation !== null;
  const requiresRemoteApiKey = providerRequiresRemoteApiKey(provider, endpoint);
  const savedKeyApplies = savedApiKeyAppliesToDraft(savedProvider, provider, endpoint);
  const savedProviderRequiresKey = savedProvider?.provider && savedProvider.endpoint
    ? providerRequiresRemoteApiKey(savedProvider.provider, savedProvider.endpoint)
    : false;
  const providerSecretState = !savedProvider?.configured
    ? "No provider configured"
    : !savedProviderRequiresKey
      ? "Current provider does not require an API key"
      : savedProvider.apiKeyConfigured
        ? "Current provider key saved in macOS Keychain"
        : "No key saved for the current provider";
  const providerValidated = core.status === "healthy"
    && validatedGeneration === core.connectionGeneration;
  const restartedAfterSave = restartBaselineGeneration === null
    || restartBaselineGeneration !== core.connectionGeneration;
  const explicitRestartFailure = restartBaselineGeneration !== null
    && !restartedAfterSave
    && ["configuration_error", "unavailable", "error"].includes(core.status)
    && restartStatusBeforeSave !== core.status;
  const restartRecoveryNeeded = restartFailed || explicitRestartFailure;
  const awaitingRestart = restartBaselineGeneration !== null
    && !restartedAfterSave
    && !restartRecoveryNeeded;
  const providerControlsLocked = providerBusy || awaitingRestart || providerLoadState !== "ready";
  const displayedProviderNotice = explicitRestartFailure
    ? {
        kind: "error" as const,
        text: "Provider settings were saved, but Keen could not confirm the restarted learning service. The previous runtime may still be active. Your learning step remains saved; retry save and restart after the service recovers.",
      }
    : providerNotice;
  const canTestProvider = savedProvider?.configured === true
    && !draftDirty
    && restartedAfterSave
    && core.status === "healthy"
    && core.client !== null;
  const testIsPrimary = learningReturn !== null
    && !providerValidated
    && canTestProvider
    && providerOperation !== "save";
  const saveIsPrimary = learningReturn === null
    || providerOperation === "save"
    || (!awaitingRestart && !providerValidated && !testIsPrimary);

  useEffect(() => {
    if (!canConfigureProvider()) return;
    let active = true;
    void getProviderConfiguration()
      .then((value) => {
        if (!active) return;
        setSavedProvider(value);
        if (value.provider) setProvider(value.provider);
        if (value.endpoint) setEndpoint(value.endpoint);
        if (value.model) setModel(value.model);
        if (value.provider && value.endpoint) {
          const matchedPreset = matchProviderPreset(value.provider, value.endpoint);
          setProviderPresetId(matchedPreset);
          setAdvancedOpen(matchedPreset === "custom");
        }
        setDraftDirty(false);
        setProviderLoadState("ready");
        setProviderNotice(null);
      })
      .catch(() => {
        if (!active) return;
        setProviderLoadState("error");
        setProviderNotice({
          kind: "error",
          text: "Keen could not read the saved provider configuration. Existing settings were not changed.",
        });
      });
    return () => {
      active = false;
    };
  }, [providerLoadAttempt]);
  const markDraftChanged = () => {
    setDraftDirty(true);
    setValidatedGeneration(null);
    setVerificationRequested(false);
    setProviderNotice(null);
  };
  const saveProvider = async () => {
    if (providerBusy) return;
    const generationBeforeSave = core.connectionGeneration;
    setRestartStatusBeforeSave(core.status);
    setProviderOperation("save");
    setProviderNotice(null);
    setValidatedGeneration(null);
    setVerificationRequested(true);
    setRestartFailed(false);
    try {
      await saveProviderConfiguration({ provider, endpoint, model, apiKey });
      setApiKey("");
      const value = await getProviderConfiguration();
      setSavedProvider(value);
      setDraftDirty(false);
      setRestartBaselineGeneration(generationBeforeSave);
      setRestartFailed(false);
      setProviderNotice({
        kind: "status",
        text: "Provider settings were saved. Keen is restarting the learning service before it verifies model access.",
      });
    } catch (error) {
      setVerificationRequested(false);
      const failure = providerSaveFailure(error);
      if (failure.outcome === "saved_restart_failed") {
        setDraftDirty(false);
        setRestartBaselineGeneration(generationBeforeSave);
        setRestartFailed(true);
        try {
          setSavedProvider(await getProviderConfiguration());
        } catch {
          // The approved failure message already states that no new runtime is assumed.
        }
      } else {
        setRestartBaselineGeneration(null);
        setRestartFailed(false);
      }
      setProviderNotice({
        kind: "error",
        text: failure.text,
      });
    } finally {
      setProviderOperation(null);
    }
  };
  const testProvider = async () => {
    if (!core.client || providerBusy) return;
    const generation = core.connectionGeneration;
    setProviderOperation("test");
    setProviderNotice(null);
    setValidatedGeneration(null);
    try {
      const result = await core.client.testProvider();
      setValidatedGeneration(generation);
      setProviderNotice({
        kind: "status",
        text: `${result.detail} ${result.provider} · ${result.model}`,
      });
    } catch (error) {
      setProviderNotice({
        kind: "error",
        text: providerTestFailure(error),
      });
    } finally {
      setProviderOperation(null);
    }
  };

  useEffect(() => {
    if (
      !verificationRequested
      || providerBusy
      || awaitingRestart
      || restartRecoveryNeeded
      || !canTestProvider
      || !core.client
    ) {
      return;
    }
    const generation = core.connectionGeneration;
    if (verificationRunGeneration.current === generation) return;
    verificationRunGeneration.current = generation;
    const client = core.client;
    queueMicrotask(() => {
      setProviderOperation("test");
      setProviderNotice({
        kind: "status",
        text: "Provider settings and the restarted learning service are ready. Verifying model access…",
      });
      void client.testProvider()
        .then((result) => {
          setValidatedGeneration(generation);
          setProviderNotice({
            kind: "status",
            text: `${result.detail} ${result.provider} · ${result.model}`,
          });
        })
        .catch((error: unknown) => {
          setProviderNotice({
            kind: "error",
            text: providerTestFailure(error),
          });
        })
        .finally(() => {
          verificationRunGeneration.current = null;
          setVerificationRequested(false);
          setProviderOperation(null);
        });
    });
  }, [
    awaitingRestart,
    canTestProvider,
    core.client,
    core.connectionGeneration,
    providerBusy,
    restartRecoveryNeeded,
    verificationRequested,
  ]);

  const openSection = (label: SettingsSection) => {
    const next = new URLSearchParams(searchParams);
    const value = settingsSectionParam(label);
    if (value) next.set("section", value);
    else next.delete("section");
    setSearchParams(next, { replace: true });
  };

  const backToOverview = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("section");
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="settings-page deeptutor-settings">
      <nav className="settings-shortcuts" aria-label="Settings sections">
          {sections.map(([label, Icon]) => (
            <button
              aria-pressed={!showingOverview && section === label || showingOverview && label === "Status"}
              className={!showingOverview && section === label || showingOverview && label === "Status" ? "active" : ""}
              key={label}
              onClick={() => openSection(label)}
            >
              <Icon aria-hidden size={15} />
              <span>{label}</span>
              <ChevronRight aria-hidden size={13} />
            </button>
          ))}
      </nav>

      <section className="settings-main" aria-labelledby="settings-heading">
        <header className="settings-page-heading">
          {!showingOverview ? <button type="button" className="settings-back" onClick={backToOverview}><ArrowLeft size={14} aria-hidden="true" />Settings</button> : null}
          <div>
            <h1 id="settings-heading">{showingOverview ? "Settings" : detailTitle(section)}</h1>
            <p>{showingOverview ? "Manage this learning workspace, its model connection, and local data boundaries." : sectionDescriptions[section]}</p>
          </div>
        </header>

        {showingOverview ? <div className="settings-overview">
          <div className="settings-runtime-strip" aria-label="Workspace readiness">
            <span><i className={`settings-runtime-dot is-${runtime.tone}`} aria-hidden="true" /><strong>Learning service</strong><small>{runtime.label}</small></span>
            <span><i className={`settings-runtime-dot is-${core.status === "demo" ? "warning" : "success"}`} aria-hidden="true" /><strong>Workspace data</strong><small>{core.status === "demo" ? "Bundled sample data is discarded when the browser preview ends." : "Local desktop workspace"}</small></span>
            <span><i className={`settings-runtime-dot is-${savedProvider?.configured ? "success" : "warning"}`} aria-hidden="true" /><strong>Model</strong><small>{savedProvider?.configured ? "Configured" : "Needs setup"}</small></span>
          </div>
          <div className="settings-overview-grid">
            {sections.map(([label, Icon]) => {
              const description = label === "Status"
                ? runtime.detail
                : label === "Model"
                  ? "Choose and verify the model Keen uses while you learn."
                  : label === "Privacy"
                    ? "See where learning data and provider credentials stay."
                    : "Review core software and included notices.";
              return <button type="button" key={label} className="settings-overview-card" aria-label={`Open ${detailTitle(label)} settings`} onClick={() => openSection(label)}>
                <span className="settings-overview-icon"><Icon size={16} aria-hidden="true" /></span>
                <span className="settings-overview-copy"><strong>{detailTitle(label)}</strong><small>{description}</small></span>
                <ChevronRight size={15} aria-hidden="true" />
              </button>;
            })}
          </div>
        </div> : null}

        {!showingOverview && section === "Model" && core.status !== "demo" ? <div className="settings-boundary" role="note">
          Remote provider keys are stored in macOS Keychain. Saving a provider restarts the local learning service before it can be tested.
        </div> : null}

        {!showingOverview && section === "Status" && (
          <div className="settings-content">
            <section className="settings-section">
              <div className="settings-section-head">
                <div><h2>Workspace status</h2><p>The services and storage Keen needs for this learning workspace.</p></div>
              </div>
              <div className="settings-list">
                <div className="settings-status-row">
                  <span><strong>Learning service</strong><small>{runtime.detail}</small></span>
                  <Badge tone={runtime.tone}>{runtime.label}</Badge>
                  {canRetry && <Button onClick={() => void core.retry()}><RotateCcw size={14} />Retry</Button>}
                </div>
                <div className="settings-status-row">
                  <span><strong>Workspace data</strong><small>{core.status === "demo" ? "Bundled sample data is discarded when the browser preview ends." : "Desktop learning data stays within Keen's local workspace boundaries."}</small></span>
                  <Badge tone={core.status === "demo" ? "warning" : "success"}>{core.status === "demo" ? "Sample only" : "Local"}</Badge>
                </div>
              </div>
            </section>
          </div>
        )}

        {!showingOverview && section === "Model" && (
          <div className="settings-content">
            {learningReturn ? <div className="settings-learning-context" role="note">
              <strong>Provider needed for this learning step</strong>
              <p>Configure and verify a provider here. Keen will then reopen this saved Deep Learn session and restore its current Recall result.</p>
            </div> : null}
            <section className="settings-section">
              <div className="settings-section-head">
                <div><h2>Choose a model provider</h2><p>Pick a known API base, enter your model and key, then let Keen save and verify the connection.</p></div>
                <Badge tone={savedProvider?.configured ? "success" : "warning"}>{providerLoadState === "loading" ? "Loading" : providerLoadState === "error" ? "Unavailable" : savedProvider?.configured ? "Configured" : "Not configured"}</Badge>
              </div>
              {!canConfigureProvider() ? <div className="settings-explanation"><div><strong>Desktop app required</strong><p>Browser Demo does not save providers or accept credentials.</p></div></div> : <div className="settings-list settings-provider-form">
                {!savedProvider?.configured ? <div className="settings-provider-intro">
                  <strong>Connect one provider to begin</strong>
                  <span>Choose provider · enter model and key · save and verify</span>
                </div> : null}
                <div className="field settings-provider-field">
                  <label htmlFor="provider-preset">Provider</label>
                  <Select
                    id="provider-preset"
                    disabled={providerControlsLocked}
                    value={providerPresetId}
                    onChange={(event) => {
                      markDraftChanged();
                      const nextPresetId = event.target.value as ProviderPresetId;
                      const nextPreset = providerPreset(nextPresetId);
                      setProviderPresetId(nextPresetId);
                      setProvider(nextPreset.transport);
                      setEndpoint(nextPreset.endpoint);
                      setModel(nextPreset.suggestedModel);
                      setAdvancedOpen(nextPresetId === "custom");
                    }}
                  >
                    <optgroup label="Built in">
                      {providerPresets.filter((preset) => preset.maturity === "built-in").map((preset) => (
                        <option value={preset.id} key={preset.id}>{preset.name}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Compatible API presets">
                      {providerPresets.filter((preset) => (
                        preset.maturity === "compatible-preset"
                        || preset.maturity === "compatibility-preview"
                      )).map((preset) => (
                        <option value={preset.id} key={preset.id}>{preset.name}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Advanced">
                      <option value="custom">Custom API base</option>
                    </optgroup>
                  </Select>
                  <div className="settings-provider-preset-note">
                    <span>{providerMaturityLabel(selectedPreset.maturity)}</span>
                    <p>{selectedPreset.description}</p>
                    {selectedPreset.maturity === "compatible-preset" ? <small>This preset fills a known API base; availability still depends on your key, model, and provider.</small> : null}
                    {selectedPreset.maturity === "compatibility-preview" ? <small>This uses the provider's OpenAI compatibility layer and may not support every Keen Agent capability.</small> : null}
                  </div>
                </div>
                <div className="field settings-provider-field">
                  <label htmlFor="provider-model">Model</label>
                  <Input
                    id="provider-model"
                    disabled={providerControlsLocked}
                    value={model}
                    onChange={(event) => {
                      markDraftChanged();
                      setModel(event.target.value);
                    }}
                    placeholder={selectedPreset.suggestedModel || "Provider model ID"}
                  />
                  <small>Use the exact model ID from your provider. Suggested values remain editable.</small>
                </div>
                {requiresRemoteApiKey ? <div className="field settings-provider-field">
                  <label htmlFor="provider-api-key">API key</label>
                  <Input
                    id="provider-api-key"
                    type="password"
                    autoComplete="off"
                    disabled={providerControlsLocked}
                    value={apiKey}
                    onChange={(event) => {
                      markDraftChanged();
                      setApiKey(event.target.value);
                    }}
                    placeholder={savedKeyApplies ? "Saved for this endpoint — enter to replace" : "Required for this endpoint"}
                  />
                  <small>{savedKeyApplies ? "A key is already stored in macOS Keychain for this API origin." : "Keen stores this key in macOS Keychain for the selected API origin."}</small>
                </div> : null}
                <div className="settings-provider-advanced">
                  <button
                    type="button"
                    className="settings-provider-advanced-toggle"
                    aria-expanded={advancedOpen}
                    onClick={() => setAdvancedOpen((open) => !open)}
                  >
                    {advancedOpen ? "Hide advanced connection" : "Advanced connection"}
                  </button>
                  {advancedOpen ? <div className="field settings-provider-field">
                    <label htmlFor="provider-endpoint">API base URL</label>
                    <Input
                      id="provider-endpoint"
                      disabled={providerControlsLocked || providerPresetId !== "custom"}
                      value={endpoint}
                      onChange={(event) => {
                        markDraftChanged();
                        setEndpoint(event.target.value);
                      }}
                      placeholder={provider === "ollama" ? "http://127.0.0.1:11434" : "https://api.example.com/v1"}
                    />
                    <small>{providerPresetId === "custom" ? "Enter the provider API base, not the final /chat/completions URL." : "This path is owned by the selected preset. Choose Custom API base to edit it."}</small>
                  </div> : null}
                </div>
                <ol className="settings-provider-progress" aria-label="Provider setup progress">
                  <li className={savedProvider?.configured && !draftDirty ? "is-complete" : "is-current"}><span>1</span><div><strong>Settings saved</strong><small>Configuration and Keychain entry</small></div></li>
                  <li className={savedProvider?.configured && !draftDirty && core.status === "healthy" && restartedAfterSave ? "is-complete" : awaitingRestart ? "is-current" : ""}><span>2</span><div><strong>Learning service ready</strong><small>Restarted with the selected model</small></div></li>
                  <li className={providerValidated ? "is-complete" : providerOperation === "test" ? "is-current" : ""}><span>3</span><div><strong>Model access verified</strong><small>Checked from the local learning service</small></div></li>
                </ol>
                {displayedProviderNotice ? <div className={`settings-explanation${displayedProviderNotice.kind === "error" ? " is-error" : ""}`} role={displayedProviderNotice.kind === "error" ? "alert" : "status"}><div><p>{displayedProviderNotice.text}</p></div></div> : null}
                <div className="settings-provider-actions">
                  {providerLoadState === "error" ? <Button
                    variant="primary"
                    onClick={() => {
                      setProviderLoadState("loading");
                      setProviderLoadAttempt((attempt) => attempt + 1);
                    }}
                  >
                    Retry provider settings
                  </Button> : null}
                  <Button
                    variant={saveIsPrimary ? "primary" : "secondary"}
                    loading={providerOperation === "save" || awaitingRestart || (providerOperation === "test" && verificationRequested)}
                    loadingLabel={providerOperation === "save" ? "Saving provider settings" : awaitingRestart ? "Restarting learning service" : "Verifying model access"}
                    disabled={providerControlsLocked || !endpoint.trim() || !model.trim() || (requiresRemoteApiKey && !apiKey.trim() && !savedKeyApplies)}
                    onClick={() => void saveProvider()}
                  >
                    {restartRecoveryNeeded ? "Retry save and verify" : "Save and verify"}
                  </Button>
                  {canTestProvider ? <Button
                    variant={testIsPrimary ? "primary" : "secondary"}
                    loading={providerOperation === "test"}
                    loadingLabel="Testing provider connection"
                    disabled={providerBusy}
                    onClick={() => void testProvider()}
                  >
                    {providerOperation === "test" ? "Testing…" : providerValidated ? "Test again" : "Test connection"}
                  </Button> : null}
                  {providerValidated && learningReturn ? <Button
                    variant="primary"
                    disabled={providerBusy}
                    onClick={() => navigate(learningReturn.to)}
                  >
                    <ArrowLeft size={14} aria-hidden="true" />Return to learning
                  </Button> : null}
                </div>
              </div>}
            </section>
          </div>
        )}

        {!showingOverview && section === "Privacy" && (
          <div className="settings-content">
            <section className="settings-section">
              <div className="settings-section-head">
                <div><h2>Data and permissions</h2><p>What stays on this Mac and which actions Keen can currently perform.</p></div>
              </div>
              <dl className="settings-facts">
                <div><dt>Learning records</dt><dd>{core.status === "demo" ? "Bundled browser sample" : "Local desktop workspace"}</dd></div>
                <div><dt>Provider secrets</dt><dd>{providerSecretState}</dd></div>
              </dl>
            </section>
          </div>
        )}

        {!showingOverview && section === "About" && (
          <div className="settings-content">
            <section className="settings-section">
              <div className="settings-section-head">
                <div><h2>Key dependencies</h2><p>Libraries that support the desktop interface and local learning workspace.</p></div>
              </div>
              <ul className="settings-notice-list">
                {notices.map((notice) => <li key={notice}>{notice}</li>)}
              </ul>
              <div className="settings-section-foot"><span>Complete license notices are included with the app in THIRD_PARTY_NOTICES.md.</span></div>
            </section>
          </div>
        )}
      </section>
    </div>
  );
}
