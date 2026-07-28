use keyring::Entry;

const SERVICE: &str = "com.keen.learning.provider-api-key";

fn entry(origin: &str) -> Result<Entry, String> {
    Entry::new(SERVICE, origin)
        .map_err(|_| "Keen could not access the macOS Keychain for this provider key.".to_owned())
}

fn unavailable_message() -> String {
    "Keen could not access the macOS Keychain. Check Keychain access and try again.".to_owned()
}

pub fn get(origin: &str) -> Result<Option<String>, String> {
    match entry(origin)?.get_password() {
        Ok(value) if !value.is_empty() => Ok(Some(value)),
        Ok(_) => Ok(None),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(_) => Err(unavailable_message()),
    }
}

pub fn has(origin: &str) -> Result<bool, String> {
    Ok(get(origin)?.is_some())
}

pub fn save(origin: &str, value: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 4_096 || value.contains(['\r', '\n']) {
        return Err("Enter a valid API key.".to_owned());
    }
    entry(origin)?
        .set_password(value)
        .map_err(|_| "Keen could not save the API key in the macOS Keychain.".to_owned())
}
