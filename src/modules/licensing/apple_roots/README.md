Public trust anchors downloaded from Apple PKI on 2026-09-30:

- https://www.apple.com/certificateauthority/AppleRootCA-G2.cer
  SHA-256 c2b9b042dd57830e7d117dac55ac8ae19407d38e41d88f3215bc3a890444a050
- https://www.apple.com/certificateauthority/AppleRootCA-G3.cer
  SHA-256 63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179

These are public certificates, not private credentials. SignedDataVerifier uses them with online revocation checks. Local Xcode StoreKit certificates are deliberately not trusted by this server.
