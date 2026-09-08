# Zonaprop desde la Mac (plan B)

Sólo hace falta si Zonaprop bloquea a GitHub Actions (aparece en rojo en "Estado de las fuentes"
del diario y llega el aviso por Telegram). Entonces:

```bash
cp launchd/com.mrbavio.caramcita.zonaprop.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mrbavio.caramcita.zonaprop.plist
```

Corre 4 veces por día (01:45, 07:45, 13:45, 19:45), 15 minutos antes de cada corrida en GitHub,
genera `snapshots/zonaprop.json` y lo sube al repo. La corrida en GitHub lo usa cuando su propio
intento contra Zonaprop falla. Si la Mac está apagada, se usa el último snapshot mientras tenga
menos de 26 horas; después Zonaprop figura como "sin datos recientes".

Para probar a mano: `launchd/zonaprop-snapshot.sh`. Log en `/tmp/caramcita-zonaprop.log`.
Para desactivar: `launchctl unload ~/Library/LaunchAgents/com.mrbavio.caramcita.zonaprop.plist`.
