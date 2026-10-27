# shellcheck shell=sh
# Deploy-owned, mounted read-only at /etc/profile.d/hermes-path.sh in the agent container.
#
# The terminal tool runs each command through a login-shell snapshot (`bash -l`). Debian's
# /etc/profile resets PATH for every non-root user, which drops the image's /opt/hermes/bin, so
# the agent's own `hermes` CLI (curator, doctor, cron, ...) is "command not found" from its
# terminal even though the gateway process has it on PATH. /etc/profile sources this directory
# after the reset, so put the launcher back in front.
case ":${PATH}:" in
  *:/opt/hermes/bin:*) ;;
  *) PATH="/opt/hermes/bin:${PATH}" ;;
esac
export PATH
