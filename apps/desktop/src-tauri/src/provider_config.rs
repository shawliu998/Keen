use serde::{Deserialize, Serialize};
use std::{
    fs, io,
    path::{Path, PathBuf},
};
use url::{Host, Url};

const CONFIG_FILE: &str = "provider-config.json";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderConfiguration {
    pub provider: String,
    pub endpoint: String,
    pub model: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderConfigurationView {
    pub configured: bool,
    pub provider: Option<String>,
    pub endpoint: Option<String>,
    pub model: Option<String>,
    pub api_key_configured: bool,
}

pub fn config_path(app_data: &Path) -> PathBuf {
    app_data.join(CONFIG_FILE)
}

pub fn load(path: &Path) -> Result<Option<ProviderConfiguration>, String> {
    if !path.exists() {
        return Ok(None);
    }
    let value: ProviderConfiguration = serde_json::from_slice(
        &fs::read(path)
            .map_err(|_| "Keen could not read the saved provider configuration.".to_owned())?,
    )
    .map_err(|_| "Keen could not read the saved provider configuration.".to_owned())?;
    validate(&value)?;
    Ok(Some(value))
}

pub fn save(path: &Path, configuration: &ProviderConfiguration) -> Result<(), String> {
    validate(configuration)?;
    let parent = path
        .parent()
        .ok_or("Keen could not prepare the provider configuration location.")?;
    fs::create_dir_all(parent).map_err(|_| {
        "Keen could not prepare private local storage for the provider configuration."
    })?;
    let bytes = serde_json::to_vec(configuration)
        .map_err(|_| "Keen could not encode the provider configuration.")?;
    let temporary = path.with_extension("json.tmp");
    fs::write(&temporary, bytes).map_err(|_| "Keen could not save the provider configuration.")?;
    set_private_permissions(&temporary)
        .map_err(|_| "Keen could not protect the provider configuration.")?;
    fs::rename(&temporary, path)
        .map_err(|_| "Keen could not finish saving the provider configuration.")?;
    set_private_permissions(path)
        .map_err(|_| "Keen could not protect the provider configuration.".to_owned())
}

pub fn validate(value: &ProviderConfiguration) -> Result<(), String> {
    if !matches!(value.provider.as_str(), "ollama" | "openai-compatible") {
        return Err("Choose Ollama or an OpenAI-compatible provider.".to_owned());
    }
    if value.endpoint.len() > 2_048
        || value.endpoint.is_empty()
        || value
            .endpoint
            .chars()
            .any(|character| character.is_whitespace() || character.is_control())
        || value.endpoint.contains(['@', '#', '?', '\\'])
    {
        return Err(
            "Enter a valid provider endpoint without embedded credentials or query parameters."
                .to_owned(),
        );
    }
    let endpoint =
        Url::parse(&value.endpoint).map_err(|_| "Enter a valid provider endpoint.".to_owned())?;
    if endpoint.fragment().is_some()
        || !endpoint.username().is_empty()
        || endpoint.password().is_some()
        || endpoint.host_str().is_none()
    {
        return Err(
            "Enter a valid provider endpoint without embedded credentials or fragments.".to_owned(),
        );
    }
    let loopback = is_loopback_url_host(&endpoint);
    let explicit_loopback_port = endpoint.port().is_some_and(|port| port > 0);
    let valid_remote_port = endpoint.port().is_none_or(|port| port > 0);
    let valid_endpoint = if value.provider == "ollama" {
        endpoint.scheme() == "http" && loopback && explicit_loopback_port
    } else {
        (endpoint.scheme() == "http" && loopback && explicit_loopback_port)
            || (endpoint.scheme() == "https" && valid_remote_port)
    };
    if !valid_endpoint {
        return Err("Ollama must use an explicit loopback HTTP endpoint; remote OpenAI-compatible endpoints must use HTTPS.".to_owned());
    }
    if value.provider == "openai-compatible" {
        let path = endpoint.path().trim_end_matches('/');
        if path.ends_with("/chat/completions") || path.ends_with("/models") {
            return Err(
                "Enter the provider API base URL, not a final chat or models resource URL."
                    .to_owned(),
            );
        }
    }
    if value.model.trim().is_empty()
        || value.model.len() > 256
        || value.model.chars().any(char::is_control)
    {
        return Err("Enter a provider model name up to 256 characters.".to_owned());
    }
    Ok(())
}

pub(crate) fn is_loopback_url_host(url: &Url) -> bool {
    match url.host() {
        Some(Host::Ipv4(address)) => address.is_loopback(),
        Some(Host::Ipv6(address)) => address.is_loopback(),
        Some(Host::Domain(_)) | None => false,
    }
}

pub fn canonicalize(mut value: ProviderConfiguration) -> Result<ProviderConfiguration, String> {
    validate(&value)?;
    value.endpoint = Url::parse(&value.endpoint)
        .map_err(|_| "Enter a valid provider endpoint.".to_owned())?
        .to_string();
    value.model = value.model.trim().to_owned();
    Ok(value)
}

pub fn remote_key_origin(value: &ProviderConfiguration) -> Result<Option<String>, String> {
    if value.provider != "openai-compatible" {
        return Ok(None);
    }
    let endpoint =
        Url::parse(&value.endpoint).map_err(|_| "Enter a valid provider endpoint.".to_owned())?;
    if endpoint.scheme() == "https" {
        Ok(Some(endpoint.origin().ascii_serialization()))
    } else {
        Ok(None)
    }
}

#[cfg(unix)]
fn set_private_permissions(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
}
#[cfg(not(unix))]
fn set_private_permissions(_path: &Path) -> io::Result<()> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{canonicalize, remote_key_origin, validate, ProviderConfiguration};

    fn configuration(provider: &str, endpoint: &str) -> ProviderConfiguration {
        ProviderConfiguration {
            provider: provider.to_owned(),
            endpoint: endpoint.to_owned(),
            model: "model".to_owned(),
        }
    }

    #[test]
    fn remote_openai_compatible_accepts_default_https_port() {
        let value = configuration("openai-compatible", "https://api.example.com/v1");
        assert!(validate(&value).is_ok());
        assert_eq!(
            remote_key_origin(&value)
                .expect("valid remote key origin")
                .as_deref(),
            Some("https://api.example.com")
        );
    }

    #[test]
    fn remote_key_account_is_bound_to_the_canonical_https_origin() {
        let first = canonicalize(configuration(
            "openai-compatible",
            "https://api.example.com:443/v1",
        ))
        .expect("first canonical provider");
        let same_origin = canonicalize(configuration(
            "openai-compatible",
            "https://api.example.com/another/path",
        ))
        .expect("same-origin provider");
        let different_port = canonicalize(configuration(
            "openai-compatible",
            "https://api.example.com:8443/v1",
        ))
        .expect("different-port provider");

        assert_eq!(
            remote_key_origin(&first).expect("first origin"),
            remote_key_origin(&same_origin).expect("same origin")
        );
        assert_ne!(
            remote_key_origin(&first).expect("first origin"),
            remote_key_origin(&different_port).expect("different origin")
        );
    }

    #[test]
    fn loopback_openai_compatible_does_not_require_a_key() {
        let value = configuration("openai-compatible", "http://127.0.0.1:8080/v1");
        assert!(validate(&value).is_ok());
        assert_eq!(remote_key_origin(&value), Ok(None));
    }

    #[test]
    fn openai_compatible_requires_an_api_base_instead_of_a_final_resource() {
        for endpoint in [
            "https://api.example.com/v1/chat/completions",
            "https://api.example.com/openai/v1/models/",
        ] {
            let error = validate(&configuration("openai-compatible", endpoint))
                .expect_err("final provider resources must be rejected");
            assert!(error.contains("API base URL"));
        }
    }

    #[test]
    fn ipv6_loopback_is_accepted_for_local_chat_providers() {
        for provider in ["ollama", "openai-compatible"] {
            let value = configuration(provider, "http://[::1]:11434/v1");
            assert!(validate(&value).is_ok());
            assert_eq!(remote_key_origin(&value), Ok(None));
        }
    }

    #[test]
    fn rejects_ambiguous_or_non_loopback_endpoints() {
        for endpoint in [
            "https://user@example.com/v1",
            "https://api.example.com/v1#fragment",
            "https://api.example.com:0/v1",
            "http://localhost:11434",
            "http://127.0.0.1",
        ] {
            assert!(validate(&configuration("ollama", endpoint)).is_err());
        }
    }
}
