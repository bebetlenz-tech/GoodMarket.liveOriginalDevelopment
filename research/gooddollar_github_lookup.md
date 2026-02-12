# GoodDollar Official GitHub + WalletConnect Source Notes

Date checked: 2026-02-12

## Goal
Identify the official GoodDollar GitHub organization/repositories and locate WalletConnect-related source code for GoodMarket integration.

## Official org / repos (best-known)
- Official GitHub organization commonly listed as: **https://github.com/GoodDollar**
- Candidate repos for integration:
  - https://github.com/GoodDollar/GoodProtocol
  - https://github.com/GoodDollar/gooddollar-app
  - https://github.com/GoodDollar/GoodServer

## WalletConnect integration source (what to pull first)
If your target is wallet connect flow, the **first repo to inspect is `gooddollar-app`** (client-side wallet UX), then `GoodServer` (if any backend session/signature glue exists).

Suggested code-search queries once network access is available:
- https://github.com/search?q=org%3AGoodDollar+walletconnect&type=code
- https://github.com/search?q=org%3AGoodDollar+@walletconnect&type=code
- https://github.com/search?q=org%3AGoodDollar+wagmi&type=code
- https://github.com/search?q=org%3AGoodDollar+web3modal&type=code

Suggested local clone + grep workflow:
```bash
git clone https://github.com/GoodDollar/gooddollar-app.git
cd gooddollar-app
rg -n "walletconnect|@walletconnect|web3modal|wagmi|reown|appkit"
```

## Environment limitation during verification
Direct outbound requests to GitHub and gooddollar.org from this environment returned HTTP 403 via CONNECT tunnel, so live in-container verification could not be completed.

Reproduce:
```bash
curl -I https://github.com
curl -I https://gooddollar.org
```

## Practical recommendation for GoodMarket
- Mirror the **frontend wallet provider + modal initialization** pattern from `gooddollar-app`.
- Keep GoodMarket's backend responsibility limited to **address/session validation** and existing UBI checks.
- Import only needed modules (provider config, connect/disconnect handlers, chain config), not whole app scaffolding.
