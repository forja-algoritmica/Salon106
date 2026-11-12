#!/usr/bin/env bash
set -euo pipefail

CHAIN="LINEA-PRODUCCION"

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta con sudo."
  exit 1
fi

if ! iptables -nL "$CHAIN" >/dev/null 2>&1; then
  echo "No existe la cadena $CHAIN."
  exit 0
fi

while iptables -S DOCKER-USER | grep -q -- "-j $CHAIN"; do
  RULE="$(iptables -S DOCKER-USER | grep -- "-j $CHAIN" | head -n 1)"
  iptables ${RULE/-A /-D }
done

iptables -F "$CHAIN"
iptables -X "$CHAIN"

echo "Reglas del proyecto retiradas."
