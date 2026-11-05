#!/bin/sh
# Create the audit network and stop its containers from reaching private networks, the cloud
# metadata service or the host itself. Public internet stays open: the target site and OpenRouter.
# Idempotent; run at boot by chaosfolk-egress.service, after Docker.
set -eu

NETWORK=chaosfolk-audits
BRIDGE=br-chaosfolk
SUBNET=172.30.0.0/24

docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create \
  --driver bridge --subnet "$SUBNET" --ipv6=false \
  -o com.docker.network.bridge.name="$BRIDGE" "$NETWORK" >/dev/null

# Rebuild our own chain so a second run does not stack duplicate rules.
iptables -N CHAOSFOLK-EGRESS 2>/dev/null || iptables -F CHAOSFOLK-EGRESS
iptables -A CHAOSFOLK-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
for range in 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 \
             192.0.0.0/24 192.168.0.0/16 198.18.0.0/15 224.0.0.0/4 240.0.0.0/4; do
  iptables -A CHAOSFOLK-EGRESS -d "$range" -j REJECT
done
iptables -A CHAOSFOLK-EGRESS -j RETURN

iptables -C DOCKER-USER -i "$BRIDGE" -j CHAOSFOLK-EGRESS 2>/dev/null || iptables -I DOCKER-USER -i "$BRIDGE" -j CHAOSFOLK-EGRESS
# Traffic to the host's own addresses goes through INPUT, not FORWARD.
iptables -C INPUT -i "$BRIDGE" -j REJECT 2>/dev/null || iptables -I INPUT -i "$BRIDGE" -j REJECT

echo "Audit network $NETWORK ready; private destinations blocked on $BRIDGE."
