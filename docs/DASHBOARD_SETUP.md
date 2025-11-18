# Dashboard Setup Guide

## Quick Setup

The dashboard uses optional dependencies that need to be installed separately.

### Installation

```bash
cd /opt/DrummondGeometry-evals
uv sync --extra dashboard
```

This installs:
- `streamlit>=1.31` - Web framework
- `plotly>=5.17` - Interactive charts
- Additional dependencies (pandas, numpy already included)

### Verification

```bash
# Check if dependencies are installed
uv run python -c "import streamlit; import plotly; print('✓ Dashboard dependencies OK')"

# Start dashboard
uv run python run_dashboard.py
```

### Production Deployment

The dashboard is automatically started by `scripts/start_all_services.sh`, which:
1. Checks if dashboard dependencies are installed
2. Installs them if missing using `uv sync --extra dashboard`
3. Starts the dashboard in a screen session

### Access

- **Local**: http://localhost:8501
- **Remote**: http://93.127.160.30:8501 (if firewall allows)

### Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'streamlit'`
**Solution**: Run `uv sync --extra dashboard`

**Issue**: Dashboard not starting
**Solution**: Check logs at `/var/log/dgas/dashboard.log`

**Issue**: Port 8501 already in use
**Solution**: 
```bash
# Find process using port
lsof -i :8501
# Kill process or change port in config/production.yaml
```

