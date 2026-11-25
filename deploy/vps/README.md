# Stały publiczny dostęp do MCP

Publiczny adres: https://vmi3696773.contaboserver.net/mcp

VPS `srv@srv` ma adres publiczny 169.58.128.206. Nazwa hosta dostawcy wskazuje
na ten adres, więc nie wymaga osobnej domeny. Systemowy Caddy uzyskuje i odnawia
certyfikat HTTPS oraz przekazuje wybrane ścieżki przez Tailscale do PC,
`100.77.87.6:3003`. Na PC nginx filtruje ścieżki i kieruje je do BentoML na 3000.

Konfiguracja systemowa VPS: `/etc/caddy/Caddyfile` (kopia w tym katalogu).
Usługa `caddy` jest enabled i active. UFW dopuszcza dodatkowo 80/tcp i 443/tcp.
Porty backendów GPU i prywatny REST nie są dostępne przez ten proxy.

Diagnostyka:
```bash
ssh srv@srv 'systemctl status caddy; sudo journalctl -u caddy -n 30'
curl --fail https://vmi3696773.contaboserver.net/health
```
Zmiana konfiguracji: skopiuj Caddyfile, `sudo caddy validate --config /etc/caddy/Caddyfile`,
a następnie `sudo systemctl reload caddy`. Nie zmieniaj innych usług na VPS.

Na PC `deploy/public-url.txt` zawiera stałą bazę HTTPS. Stary supervisor
`bento-public-tunnel` został wyłączony, żeby nie nadpisywał tego adresu.
Caddy, nginx i Tailscale muszą działać, a sam PC musi być uruchomiony.

Claude web: Customize → Connectors → BentoML GPU. Połączenie autoryzowane przez
OAuth. W rozmowie: plus → Connectors → włącz BentoML GPU. Źródła danych dobiera
agent, używając importu URL/Kaggle lub własnego środowiska wykonawczego.
