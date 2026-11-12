#!/usr/bin/env bash
set -euo pipefail

CHAIN="LINEA-PRODUCCION"
NETWORK="linea-produccion_app_net"

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta con sudo."
  exit 1
fi

BRIDGE="$(docker network inspect "$NETWORK" --format '{{ index .Options "com.docker.network.bridge.name" }}')"
if [[ -z "$BRIDGE" || "$BRIDGE" == "<no value>" ]]; then
  ID="$(docker network inspect "$NETWORK" --format '{{.Id}}')"
  BRIDGE="br-${ID:0:12}"
fi

if ! iptables -nL "$CHAIN" >/dev/null 2>&1; then
  iptables -N "$CHAIN"
fi

if ! iptables -C DOCKER-USER -i "$BRIDGE" -j "$CHAIN" 2>/dev/null; then
  iptables -I DOCKER-USER 1 -i "$BRIDGE" -j "$CHAIN"
fi

iptables -F "$CHAIN"

iptables -A "$CHAIN" -m conntrack --ctstate NEW \
  -m limit --limit 5/min --limit-burst 5 \
  -j LOG --log-prefix "LP-FW: " --log-level 4

echo "Monitoreo IPv4 activo en $BRIDGE."
echo "Modo observacion: no se bloquean destinos."
