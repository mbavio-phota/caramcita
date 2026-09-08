# Fuentes que se corren desde la Mac

Dos casos usan la Mac (IP residencial) en vez de GitHub Actions:

- **Lequio Propiedades** (`run_from: mac` en `sources.yaml`): su servidor corta la conexión desde las
  IPs de GitHub. Sin este job, Lequio simplemente no aparece (sin error).
- **Zonaprop**, como respaldo: hoy pasa el challenge de Cloudflare desde GitHub, pero si deja de pasar
  la corrida usa el snapshot de la Mac.

Instalación (una vez):

```bash
cp launchd/com.mrbavio.caramcita.snapshot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mrbavio.caramcita.snapshot.plist
```

Corre 4 veces por día (01:45, 07:45, 13:45, 19:45), 15 minutos antes de cada corrida en GitHub,
genera `snapshots/<slug>.json` y los sube al repo. Si la Mac está apagada, GitHub usa el último snapshot
mientras tenga menos de 26 horas; después esa fuente figura como "sin datos recientes".

Requisito: `git push` sin pedir clave desde launchd (`gh auth setup-git` lo configura).

Para probar a mano: `launchd/snapshot.sh`. Log en `/tmp/caramcita-snapshot.log`.
Para desactivar: `launchctl unload ~/Library/LaunchAgents/com.mrbavio.caramcita.snapshot.plist`.
