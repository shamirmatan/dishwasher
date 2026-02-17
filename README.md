# Dishwasher Automation

Start a Bosch dishwasher remotely via the Home Connect API, triggered from GitHub Actions.

## Setup

### 1. Register at Home Connect Developer Portal

1. Go to https://developer.home-connect.com/
2. Create an account and register an application
3. Note your **Client ID** and **Client Secret**
4. Set the application type to "Device Flow"

### 2. Pair Your Dishwasher

Make sure your dishwasher is connected to Wi-Fi and paired in the **Home Connect** mobile app.

### 3. Run the Auth Setup

```bash
pip install requests
python setup_auth.py
```

This will:
- Start the OAuth2 Device Flow
- Print a URL to open in your browser
- Wait for you to authorize
- List your appliances and print the values needed for GitHub secrets

### 4. Configure GitHub Secrets

In your repo's Settings > Secrets and variables > Actions, add:

| Secret             | Value                                      |
| ------------------ | ------------------------------------------ |
| `HC_CLIENT_ID`     | Your Client ID from the developer portal   |
| `HC_CLIENT_SECRET` | Your Client Secret from the developer portal |
| `HC_REFRESH_TOKEN` | Refresh token from `setup_auth.py` output  |
| `HC_HAID`          | Appliance haId from `setup_auth.py` output |

### 5. Enable Remote Start

On the dishwasher itself, enable the **Remote Start** option. This is a physical button/setting that must be activated before each remote start.

## Usage

Go to **Actions** > **Start Dishwasher** > **Run workflow** in the GitHub UI.

## Troubleshooting

| Error                        | Fix                                                                 |
| ---------------------------- | ------------------------------------------------------------------- |
| Token refresh failed (401)   | Re-run `setup_auth.py` to get a new refresh token                   |
| Remote Start not enabled     | Press the Remote Start button on the dishwasher before triggering   |
| Appliance offline (retries)  | Check that the dishwasher is powered on and connected to Wi-Fi      |
| HTTP 409 (conflict)          | The dishwasher may already be running a program                     |
