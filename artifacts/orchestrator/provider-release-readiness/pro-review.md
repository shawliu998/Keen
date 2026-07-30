# BYOK provider setup — Pro review

Date: 2026-07-28

## Review boundary

The review covered the native Settings provider catalog, API-base ownership,
save/restart/connectivity state machine, first-provider guidance, validation
claims, and public-distribution limits. The user explicitly excluded live
vendor-account acceptance.

## First review

Decision: `B) REVISE`

Required changes:

1. Separate built-in transport, compatible preset, and compatibility preview;
   do not imply that a convenience mapping is vendor certification.
2. Make catalog presets own known API bases and make Custom own an explicit
   API-base contract; prevent final resource URLs and double path assembly.
3. Implement `Save and verify` as
   Editing → Saving → Sidecar restart → Connectivity testing →
   Verified/Failed.
4. Keep first-provider guidance local to Settings, without onboarding,
   navigation, or Agent expansion.
5. Describe tests as catalog/path/mock-flow contract validation rather than
   live provider support.

## Final review

Decision: `A) ACCEPT`

The final review confirmed that all five requirements were satisfied:

- provider maturity and compatibility boundaries are explicit;
- catalog and Custom API-base ownership are distinct;
- saving, sidecar generation change, connectivity testing and verified/failed
  outcomes are separate;
- the guidance remains inside Settings;
- documentation and tests do not claim live vendor certification.

The reviewer found no must-fix product or code defect within the stated
boundary. Developer ID signing, notarization, and clean-Mac installation remain
external public-distribution gates, not claims made by this implementation.
