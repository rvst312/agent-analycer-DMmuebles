# Auditoría: lectura de planos y propuestas de presupuesto

Fecha: 9 de octubre de 2026. Alcance: `carpinteria-ai` (backend FastAPI + LangGraph, frontend Next.js), los 23 planos subidos que hay en `backend/uploads`, los 22 presupuestos guardados en `local_dev.db`, la tarifa oficial `TABLA DE PRECIOS actualizada Dani.pdf` y las bases de precios exportadas en `~/Downloads`.

## 1. Resumen ejecutivo

La app ya tiene una arquitectura correcta: visión por partidas con familias, calculadora paramétrica a partir de la tarifa, corrección con IA y lecciones aprendidas. El problema no es el diseño sino tres cosas concretas:

1. **La visión lee las imágenes a baja resolución y no usa el texto del PDF.** Casi todos los planos son PDF vectoriales con las cotas y acabados como texto real. Hoy se reducen a JPEG de 1400 px y se leen "a ojo", y por eso salen medidas a máximos, puertas de 67 cm "fuera de tarifa" y materiales inventados.
2. **Reglas de interpretación que faltaban.** El vocabulario de los estudios (CASCO, FRENTES, MALETERO, ALTILLO, bisagras ocultas, puertas simuladas, se reutiliza, mediciones Presto) no estaba codificado. He escrito un glosario y lo he dejado conectado al prompt de visión.
3. **Seis errores de cálculo con impacto en euros**, todos reproducidos con el motor real y corregidos con tests en esta auditoría (sección 4).

Además, la tarifa cargada en la app cubre solo 4 de las 7 páginas del PDF de tarifa (faltan extras de puertas, panelados, puertas de marco de madera, pasamanos), y no existe todavía ningún mecanismo de "propuestas" ni de comparativa con mercado. En la sección 7 hay un plan por prioridades para eso.

## 2. Cómo lee hoy la app un plano

1. Subida → cada PDF se convierte a PNG por página (con corrección automática de giro) para el visor.
2. Pasada 1 (`_detect_view_codes`): envía el PDF crudo entero a Claude para sacar los códigos de vista (A01, PL…).
3. Pasada 2 (`_analyze_partidas_plan`): una sola llamada con todas las páginas reducidas a 1400 px, que devuelve un JSON de partidas (familia, medidas, material, apertura, cantidad, página y recuadro).
4. Cálculo (`_price_partidas` + `tarifa.py`): armarios y vestidores por módulos + puertas + interiores; puertas de paso y baldas por tarifa paramétrica; rodapié por búsqueda en la base de precios (Chroma); baño, varios, cerramientos y "otro" quedan pendientes.
5. Revisión humana, corrección con IA (edita el JSON de partidas y recalcula) y envío a Holded.

Lo que NO hace hoy: no usa la capa de texto del PDF, no hace una segunda pasada de zoom por partida, no reconcilia mediciones del cliente con dibujos, no propone alternativas ni compara con el mercado, y no tiene concepto de "variante" de precio.

## 3. Qué planos ha visto y qué pasó con cada uno

| Proyecto | Estilo del documento | Partidas / líneas | Resultado real |
|---|---|---|---|
| Armarios A06–A08 + puertas (6 págs, 1440×810) | Dossier con tabla ACABADOS (exterior / interior / tirador) | 23–40 líneas | Usado para las pruebas iniciales; "puerta plafonada laminada" se trata como melamina lisa por regla de negocio |
| GOYA (dosplanos, 11 págs) | Croquis de reforma con notas del cliente | 16 partidas, 29 líneas, 3 correcciones | Cobra cuerpo de armario en "puertas simuladas" y 642 € en un vestidor "reutilizado"; rodapiés 25 cm y 4 cm fuera de tabla |
| ROSALES (CAD arquitecto + mediciones Presto) | Plano por mueble con cajetín + documento de mediciones | 88 líneas, 63.122 € | Partidas DUPLICADAS: cada armario sale del plano (A1…A13) y otra vez de la medición (A1-2…A13-2); puerta acorazada cobrada a 370 € como puerta de paso |
| VALLE DE BELAGUA 22 (18 págs giradas) | Dossier interiorismo con submódulos A06-1…A07-5 | 80 líneas, 33.492 € | 10 puertas "estándar" y 4 "suelo a techo" pendientes por falta de alto; un vestidor con "alto 520 cm"; frentes de cristal ahumado tratados como vestidor sin puertas |
| CARACAS 11 (WINK, 12 págs) | Dossier por mueble con alzado de frentes + distribución interior y cuadro de acabados | 15 partidas, 54 líneas, 32.180 €, 2 correcciones | 10 puertas de paso cobradas con tarifa rasomuro por "bisagras ocultas" (+2.600 €); 10 puertas de armario de 63–67 cm pendientes; 14 maleteros pendientes; grosor 4 cm de baldas ignorado |

## 4. Errores confirmados y corregidos

Reproducidos con `_price_partidas` sobre la tarifa real antes de tocar nada:

| # | Error | Dónde | Efecto en un caso real | Corrección aplicada |
|---|---|---|---|---|
| 1 | "bisagras ocultas" (plural) disparaba la tarifa **rasomuro** (base 720 €) en vez de normal (370 €) + extra | `pricing_agent._price_partidas` | CARACAS PA13/PA14: 1.008 € y 1.116 € por puerta en vez de 723,50 € y 871,50 € → unos 2.600 € de más en 10 puertas | Detección por palabra completa; "oculta" junto a bisagra/guía/carril/herraje es herraje. Nuevos extras de tarifa en config: bisagras ocultas 150, resbalón magnético 30, plinto 80/puerta, autocierre rasomuro 150 |
| 2 | Grosor de balda no leído ("Grosor balda 40mm") | rama `balda_pared` | CARACAS E01/E02: 68 € por balda en vez de 85 € (12 baldas, 204 € de menos). LED vertical estimado con el ancho (0,5 ml) en vez del alto | Regex tolerante, nº de baldas desde items, LED vertical usa el alto |
| 3 | MALETERO / ALTILLO "fuera de tarifa" (pendiente) | `tarifa.precio_interior` | CARACAS: 14 líneas pendientes; ROSALES: 13 líneas pendientes | La tarifa "Módulo + maletero" ya lo incluye → línea a 0 € con nota, no pendiente. Zapatero = baldas. Huecos (TV, espacio) a 0 € |
| 4 | Puerta **acorazada** cobrada como puerta de paso normal | rama `puerta_paso` | ROSALES PE2: 370 € por una acorazada | Acorazada / blindada / de seguridad → pendiente (consultar) |
| 5 | "REUTILIZADO" se presupuesta a máximos | `_price_partidas` | GOYA vestidor reutilizado: 642 €; A3 "interior se reutiliza" pendiente | "se reutiliza / se mantiene / no se presupuesta / incluido en cocina" → 0 € con nota. "Igualando al existente" NO es reutilizado |
| 6 | "PUERTAS SIMULADAS" cobra cuerpo de armario | `_precio_un_armario` | GOYA P2: 700 € de cuerpo inexistente | Simuladas / solo frentes / sin cuerpo → solo puertas |
| 7 | Puerta de paso "estándar" sin cota queda pendiente | rama `puerta_paso` | BELAGUA: 10 puertas a 0 € (unos 3.700 € sin presupuestar) | Estándar / 203 → block 2030×725 con nota |

Cada una tiene su test en `backend/tests/test_tarifa_reglas.py`. También se ha arreglado la colección de tests (`tests/conftest.py`): `test_estimates.py` y `test_knowledge.py` fallaban en macOS porque `UPLOAD_DIR` por defecto es `/app/uploads`.

## 5. El lenguaje de los planos (lo que la app ahora "sabe")

El glosario completo está en `backend/agents/glosario_planos.md` y se inyecta en el prompt de sistema de la visión (con caché) y en el corrector. Las claves que más errores evitan:

- Cotas: punto con dos decimales = metros; 2–3 cifras = cm; 4 cifras = mm. "0.20 TAPETA" es la tapeta, no el alto.
- CASCO = interior; FRENTES = puertas; MALETERO = ALTILLO = incluido en el módulo; TAPETA = remate; COSTADO VISTO = extra.
- Diagonales discontinuas = abatible; flechas ↔ = corredera; "con dedal" = corredera con uñero; "guía oculta" = herraje, no rasomuro.
- Bisagras ocultas = extra de 150 €, NO rasomuro. Rasomuro solo si lo dice de la puerta (rasomuro, enrasada, cerco de aluminio).
- LAMINADO = melamina (siempre lisa). RAL 9010/9003/9002 = laca blanca; RAL 7043 = laca oscura. Cerezo / nogal / sapeli = consultar.
- "Con rehundido" / baquetón / moldura = plafonado. "Frente pantografiado" = pantografiado.
- Mediciones Presto: las cantidades de la medición mandan; un código = una partida (no duplicar con el dibujo). "DAR PRECIO" = valorar; "OPCIÓN ROBLE" = variante; "PVP" = precio que propone el cliente.
- "Se reutiliza / se mantiene" = 0 €. "Puertas simuladas" = solo frentes. "Acorazada" = fuera de tarifa. "Estándar 203" = block 2030×725.

## 6. Huecos entre la tarifa PDF y la tarifa de la app

`tarifa_config.json` recoge fielmente las páginas 1–4 del PDF (baldas, módulo, puerta de armario, interiores, rodapié, puertas de paso). Faltan:

| Página PDF | Contenido | Estado en la app |
|---|---|---|
| 2 | Interiores: acabado melamina especial +50 %, cristal 8 mm +50 %, laca blanca +100 % sobre baldas/cajones | No se aplica a interiores (siempre precio stock) |
| 2 | "Descuentos hasta 20 % según cliente y cantidad" (baldas) | No modelado |
| 4 | Extras de puerta de paso: bisagras ocultas 150, resbalón magnético 30, plintos 80/puerta, autocierre 150 | **Añadido en esta auditoría** |
| 4 | Acabado "Roble 20 %" y una fila "30 %" sin etiqueta (¿roble teñido?) | Roble sí; la fila 30 % hay que aclararla |
| 4 | Checklist "A tener en cuenta": situación, mano, cerco, condena, manivela, color herraje, tapetas, plinto | La visión no captura mano, condena ni tapetas |
| 5 | Panelados (roble, nogal, melamina friso, palillería, puerta DM lacada, panelado puerta principal 450 €, embocadura) | Sin familia ni tarifa. "Chapado interior puerta de acceso" (CARACAS, ROSALES) encajaría en "panelado puerta principal 450 €" |
| 6 | Puertas de marco de madera (1050 €/puerta sencilla 4 palos, +100 € palo, −10 % <60 cm), correderas por el exterior (carril visto +150, oculto +200, empotrado +200), guía de techo Klein 200, muelle 55 | Sin tarifa. Es justo lo que piden GOYA P6 y BELAGUA A05-2 (cerramientos acristalados) |
| 7 | Pasamanos tipo U 50 €/ml | Sin tarifa (ROSALES M4 pide 20,25 ml) |

Base de precios: en Chroma hay 50 entradas (38 rodapiés + 12 puertas), pero en `~/Downloads/base_de_precios_2026-05-10.csv` hay 4.151 filas que son la tarifa desplegada en todas sus combinaciones. No merece la pena cargarlas: la calculadora paramétrica ya las genera. La base de precios debería quedar para lo que no es paramétrico: manillas, tiradores, guías, herrajes especiales y referencias de mercado.

## 7. Plan de mejoras por prioridad

### Hecho en esta auditoría
- Glosario del lenguaje de planos inyectado en visión y corrector (`glosario_planos.md`).
- Capa de texto del PDF (`extract_pdf_text_pages`) enviada a la visión junto a las imágenes, con la regla de reconciliación de mediciones.
- Modelo de visión actualizable por entorno (`VISION_MODEL`, por defecto Claude Opus 5.5 con razonamiento adaptativo; pasadas auxiliares con Haiku 5.5), prompt de sistema cacheado, pasada de códigos con las páginas ya renderizadas en vez del PDF crudo de 8 MB.
- Siete correcciones de cálculo con tests (sección 4) y arreglo de la suite de tests.

### Siguiente tanda (1–2 semanas)
1. **Lectura en dos pasadas con zoom.** Pasada 1 detecta partidas y recuadros (ya existe). Pasada 2: por cada partida, enviar el recorte a resolución completa (ya se genera para el visor) y pedir SOLO medidas, nº de hojas, interior y acabados. Es la mejora de precisión más grande que queda: las cotas de los planos CAD (83,5 / 219) son ilegibles a 1400 px.
2. **Reconciliación de mediciones.** Detectar documentos Presto por su cabecera, parsearlos a partidas estructuradas (código, cantidad, PVP, opciones) y fusionarlos por código con las del dibujo. Evita los duplicados de ROSALES (unos 7.000 € de más).
3. **Variantes de precio por partida.** Campo `variantes` (roble +20 %, cerezo/nogal consultar, melamina −25 %) que la visión rellena cuando el cliente pide "OPCIÓN X" y la calculadora valora. En Holded salen como líneas opcionales.
4. **Completar la tarifa** con las páginas 5–7 y el acabado de interiores (sección 6), y dos decisiones de negocio que hoy bloquean líneas: puertas de armario de 60–70 cm (hoy consultar; el 40 % de las hojas de CARACAS) y el salto de módulo en 120 cm (134 cm cuesta el doble que 120 cm).
5. **Rodapié sin metros.** Estimar los ml a partir de las superficies de la planta (los dossieres rotulan los m² por estancia) y dejarlos como "estimado, confirmar".

### Propuestas y comparativa de mercado (2–4 semanas)
6. **Motor de propuestas determinista** (`agents/propuestas.py`): para cada partida recalcula alternativas con la propia tarifa y devuelve sugerencias con el ahorro en euros. Ejemplos que ya se pueden derivar de los planos vistos: "ancho 134 cm → 2 módulos (1.680 €); con 120 cm sería 1 módulo (840 €)"; "interior en laca blanca +100 %: en melamina ahorras X"; "puerta 67 cm fuera de tarifa: con 3 hojas de 45 cm entra en tarifa"; "rodapié 25 cm no está en tarifa, el más cercano es 20 cm doble dibujo a 22 €/ml"; "corredera +50 %: en abatible ahorras Y".
7. **Capa de mercado.** Un `mercado_config.json` con horquillas por familia (€/ud, €/ml, €/m²), fuente y fecha, editable desde la pantalla de tarifa como hoy la tarifa. El presupuesto muestra junto a cada grupo dónde cae respecto a la horquilla (bajo / medio / alto). Se alimenta a mano y, opcionalmente, con una búsqueda web asistida que proponga actualizaciones para que Dani las apruebe.
8. **"Asesor" del presupuesto.** Botón que manda a Claude el presupuesto, la tarifa, el glosario y las horquillas de mercado y devuelve 3–5 recomendaciones (qué partidas están fuera de mercado, qué alternativas ofrecer al cliente, qué cambiar en la tarifa) con los números ya calculados por el motor de propuestas. La IA redacta, no inventa precios.

## 8. Comparativa con el mercado (orientativa)

Referencias públicas de España recogidas en octubre de 2026. Son horquillas de portales y prensa, no tarifas oficiales; sirven para posicionar, no para fijar precio.

| Partida | Tarifa DN (sin IVA) | Mercado | Lectura |
|---|---|---|---|
| Puerta de paso lisa lacada blanca instalada (block 2030×725, sin manilla) | 370 € | Básica instalada ~200 € + IVA; block de almacén 59–159 € + montaje 15–30 €; carpintería a medida 350–600 € | DN está en la franja media-alta. Para obras "estándar" un competidor de almacén baja a la mitad; para a medida, en línea |
| Puerta corredera lisa lacada (misma base +50 %) | 555 € | 400–700 € instalada con guía | En línea |
| Armario empotrado 120×240×60, 2 puertas lisas, interior melamina | 1.020 € de cuerpo + puertas (unos 850 €/ml) | 450–1.200 €/ml; 1 m × 2,2 m ≈ 1.000 € + IVA; total habitual 1.400–1.900 € | En la mitad de la horquilla. Con interior en laca blanca (+100 %) se va por encima del máximo de mercado |
| Rodapié DM lacado 12 cm instalado | 14 €/ml | Material 2–4,5 €/ml + colocación 3–17 €/ml (5–21 €/ml) | Competitivo |

Fuentes: [Habitissimo, puertas lacadas](https://www.habitissimo.es/presupuestos/puertas-lacadas), [Obramat, puerta block lacada 72,5](https://www.obramat.es/productos/puerta-interior-en-block-lacada-blanca-3c-72-5-cm-derecha-25140141.html), [El Español, armarios a medida 2026](https://www.elespanol.com/mujer/interiorismo/20260607/carpinteros-coinciden-poner-armario-medida-euros-ahora-supera/1003744268652_0.html), [Acierto, precio armario empotrado](https://www.acierto.com/prestamos/precio-armario-empotrado/), [Habitissimo, armarios empotrados](https://www.habitissimo.es/presupuestos/armarios-empotrados), [Trustlocal, carpintero 2026](https://trustlocal.es/coste/carpintero-coste/), [Habitissimo, rodapié](https://www.habitissimo.es/presupuestos/rodapie), [Obramat, rodapié DM lacado](https://www.obramat.es/productos/pack-5-rodapies-dm-lacado-blanco-directo-2250-x-90-x-12-mm-10732512.html). El generador de precios de CYPE (capítulo L, carpintería) es la referencia técnica más seria para cargar en `mercado_config.json`; no se ha podido consultar la partida exacta en esta sesión.

## 9. Decisiones que solo puede tomar Dani

1. ¿"Melamina textil" (Cáctus, lino, Graff) es melamina stock (0 %) o especial (+50 %)? Hoy se trata como stock.
2. Puertas de armario de 60–70 cm: ¿tramo nuevo (por ejemplo +15 %) o seguir en "consultar"?
3. ¿Un armario de 121–134 cm se presupuesta como 2 módulos a precio completo, o como 1 módulo + 1 de ≤60 cm (−35 %)?
4. La fila "30 %" sin etiqueta en acabados de puerta de paso del PDF: ¿roble teñido?
5. Rodapié 25 cm con moldura y 4 cm (GOYA): ¿precio nuevo o consultar?
6. Páginas 5–7 de la tarifa (panelados, cerramientos de marco de madera, pasamanos): ¿se cargan como familias con tarifa?
7. ¿Las manillas y tiradores siguen fuera del presupuesto cuando la medición del cliente da PVP?

## 10. Prueba real con CARACAS 11 (visión nueva)

Análisis en vivo con Claude Opus 5.5, glosario y texto del PDF, esfuerzo medio: 76 s.

| | Antes (guardado en BD) | Ahora |
|---|---|---|
| Subtotal | 26.595 € | 22.208 € |
| Líneas pendientes | 18 | 9 |
| Puertas de paso | 10, todas con tarifa rasomuro | 8 (5 de 240 cm y 3 de 270 cm, que es lo que marca la planta), tarifa normal + bisagras ocultas |
| Baldas E01/E02 | 6 + 6 a 68 € | 5 + 5 a 85 € (las dibujadas, grosor 4 cm) |
| Maleteros | 14 pendientes | Incluidos en el módulo |
| Proyecto | No detectado | "Caracas 11" |

Pendientes que quedan y por qué: 9 puertas de armario de 63–67 cm (decisión de tramo), espejo retroiluminado, 3 embocaduras y el chapado de la puerta de acceso (sin familia de tarifa), y los metros de rodapié (el plano no los da).

Dos problemas encontrados al probar en vivo y ya corregidos:
- Pedir al modelo "escribe tu razonamiento" en `<raw_reasoning>` hacía que Opus 5.5 rechazara el análisis (filtro `reasoning_extraction`). Ahora pide un `<resumen_lectura>`.
- Con esfuerzo alto y el razonamiento oculto, el stream pasaba más de 10 minutos sin datos y se cortaba (27 min sin resultado). Ahora el razonamiento va resumido, el esfuerzo es `medium` por defecto (`VISION_EFFORT`) y la espera máxima sin datos es de 5 minutos.
