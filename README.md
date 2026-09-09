# BTC Spot CVD — publicación automática

Consulta APIs REST públicas, genera CVD spot BTC on-demand para 15m/1h/4h/24h, valida el contrato JSON y publica únicamente resultados válidos mediante GitHub Pages. No usa API keys, secretos, WebSockets, base de datos ni procesos locales permanentes.

## Arquitectura

GitHub Actions ejecuta a las **07:43 Europe/Madrid** todos los días (con ajuste automático de horario de verano). El workflow usa `btc_cvd.py --json`, valida el resultado mediante `publish.py` y despliega `public/btc_cvd.json` a Pages. Si cualquier paso falla, no hay despliegue: la última versión buena permanece publicada.

URL una vez creado como repositorio público y activado Pages con fuente **GitHub Actions**:

```text
https://USUARIO.github.io/REPOSITORIO/btc_cvd.json
```

## Validación local

```bash
python3 -m unittest -v
python3 publish.py
python3 -m json.tool public/btc_cvd.json >/dev/null
```

El JSON tiene `generated_at` UTC y `stale_after`. El consumidor debe considerarlo obsoleto cuando la hora actual sea posterior a `stale_after`. El margen es de 25 horas para tolerar pequeños retrasos del scheduler sin aceptar silenciosamente dos días sin actualización.

## Comportamiento ante fallos

- Un fallo aislado de una API queda en `exchanges.<nombre>.error`; sus ventanas sin cobertura se excluyen y aparecen en `excluded_exchanges`.
- Si alguna ventana queda sin ninguna fuente completa, el publicador rechaza el resultado y conserva el último despliegue bueno.
- No se inventan ni extrapolan trades. Una fuente sólo entra en el agregado cuando alcanza el inicio de la ventana.
- Un error de proceso, JSON inválido, contrato incompleto o fecha anómala cancela el despliegue y conserva el último JSON bueno.
- Los logs de Actions muestran pruebas, generación, errores REST y despliegue sin credenciales.

## Coste y mantenimiento

Coste previsto: **$0/mes** usando un repositorio público, runners estándar y GitHub Pages. GitHub puede retrasar jobs programados; por eso se evita el minuto 00. GitHub desactiva workflows programados en repositorios públicos sin actividad durante 60 días, por lo que puede ser necesario reactivarlo periódicamente desde Actions.

## Datos y metodología

- Binance `BTCUSDT`: proxy de velas 1m con `takerBuyBaseVolume` (`KLINE_TAKER_PROXY`).
- Coinbase `BTC-USD`: trades paginados; el lado publicado es maker y se invierte (`INDIVIDUAL_TRADES`).
- OKX `BTC-USDT`: trades paginados con lado taker (`INDIVIDUAL_TRADES`).
- Bybit `BTCUSDT`: trades recientes limitados; normalmente queda excluido por cobertura (`RECENT_TRADES_LIMITED`).

Todos los volúmenes agregados están en BTC. `GOOD` significa cuatro exchanges completos, `PARTIAL` dos o tres y `POOR` cero o uno.

## Seguridad

El repositorio contiene sólo código, workflow y documentación. `public/` se genera temporalmente en el runner, no se versiona. No hay secretos, rutas personales ni credenciales.
