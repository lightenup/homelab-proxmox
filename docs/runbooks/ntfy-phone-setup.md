# ntfy Phone Setup

Set up the ntfy Android app to receive push notifications from the self-hosted ntfy server
(spec `082`, FR-015).

## Prerequisites

- ntfy is deployed and reachable at `https://ntfy.hus-sky.no` (LAN or tailnet).
- The owner's password is in the password manager (entered at `ansible-vault edit` time,
  never stored in this repo).
- Tailscale is installed on the phone (for away-from-home delivery).

## Install the app

1. Install **ntfy** from the [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   or [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/).

## Add the server

1. Open the app.
2. **Settings** → **Default server** → enter `https://ntfy.hus-sky.no`.
3. **Settings** → **Manage users** → **Add user**:
   - Username: `owner`
   - Password: from the password manager.
4. Verify the user is saved (it will appear in the user list).

## Subscribe to topics

1. Tap the **+** button (or long-press the subscription list).
2. Subscribe to `alerts` (Alertmanager notifications).
3. Subscribe to `hermes` (Hermes Agent scheduled jobs, spec `083`).
4. For each topic, confirm **"Instant delivery"** is toggled on.

## Notification channel (optional)

To make critical alerts break through Do Not Disturb:

1. **Settings** → **Notifications** → select the `alerts` topic.
2. Set the notification channel to **Urgent** (or the highest available importance).
3. In Android **Settings** → **Apps** → **ntfy** → **Notifications** → select the channel →
   enable **"Interrupt Do Not Disturb"**.

## Battery optimisation (required for reliable delivery)

Android's battery saver can kill the persistent connection. Disable it for ntfy:

1. Android **Settings** → **Apps** → **ntfy** → **Battery**.
2. Set to **Unrestricted**.

Alternatively: **Settings** → **Apps** → **Special access** → **Battery optimization** →
**ntfy** → **Don't optimize**.

## Tailscale (away-from-home delivery)

1. Install [Tailscale](https://tailscale.com/download/android) if not already present.
2. Log in with the estate's Tailscale account.
3. **Settings** → **Always-on VPN** → enable.

With Always-on VPN, the phone stays on the tailnet even when Wi-Fi is off, so ntfy's
persistent connection survives mobile-data transitions.

## Verifying reach

Open a browser on the phone (LAN or tailnet) and navigate to:

```
https://ntfy.hus-sky.no/v1/health
```

Expected: `{"healthy":true}`.

## What a 72-hour gap means (FR-013)

ntfy caches messages for **72 hours** after they are published. If the phone is unreachable
for less than 72 hours, it receives all cached messages on reconnect. If the phone is
unreachable for more than 72 hours, older messages are deleted by design and will not be
delivered. This is not a bug — it is the configured retention window (`cache-duration: "72h"`).

## Troubleshooting

| Symptom | Check |
|---|---|
| No notifications at all | Is the app in the foreground at least once after install? Android may not start the service until the user opens the app. |
| Notifications delayed by minutes | Battery optimisation not set to Unrestricted. |
| No notifications away from home | Tailscale not connected, or Always-on VPN not enabled. |
| `{"healthy":false}` from `/v1/health` | ntfy container is down — check the LXC. |
