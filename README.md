# QuantNifty Next

Live NIFTY options analytics using INDstocks/INDMoney market data.

## Runtime configuration

The INDstocks access token is supplied only through the runtime environment variable `INDSTOCKS_API_TOKEN` (the service also accepts the legacy `INDSTOCKS_TOKEN` alias for compatibility). Secrets are never committed to the repository.

## Safety

QuantNifty Next is currently **read-only**. Order placement, modification, cancellation, and execution controls are disabled.

## Deployment

The production service is configured as a Python Render web service from the `main` branch, with health checks served by `/health`.
