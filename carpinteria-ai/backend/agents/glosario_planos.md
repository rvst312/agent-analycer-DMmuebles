# Glosario del lenguaje de planos de carpintería (DM Muebles)

Este documento se inyecta en el prompt de visión. Recoge cómo rotulan los planos los
estudios y arquitectos con los que trabajamos (WINK, dosplanos, CAD de arquitecto,
interiorismo con páginas giradas, mediciones tipo Presto) y cómo se traduce cada
rótulo a nuestras familias y a nuestra tarifa. Si un rótulo del plano contradice una
regla de aquí, manda el plano; si el plano es ambiguo, manda esta guía.

## 1. Estilos de documento que recibimos

- **Dossier de interiorismo (p. ej. WINK, "03. PROPUESTA - LOOK & FEEL")**: una página
  por mueble. Título tipo `Armario_ A05_Dormitorio 2` o `Salón y pasillo_E01-E02_Estanterías`.
  Planta con el mueble sombreado, alzado de FRENTES (puertas) a la izquierda y alzado de
  DISTRIBUCIÓN INTERIOR a la derecha, cotas en metros (2.70, 0.59), cuadro ACABADOS con
  muestras ("Lacado blanco_Frente pantografiado", "Melamina Textil Cáctus", "Laminado Olmo
  caramelo"). Una página "Puertas de paso" con puntos de color en planta = ubicación de
  cada tipo de puerta y su cantidad.
- **Plano CAD de arquitecto (p. ej. ROSALES, cajetín "Nº del plano / Nombre del plano /
  Nombre del proyecto")**: códigos de puerta `PL`, `PM`, `PD`, `PC`, `PE`; rótulos tipo
  "PUERTA DM LACADO H 212cm", "una hoja abatible maciza RAL 9010", cotas en cm (83,5 / 219)
  en azul; planos de armario `A1…A13` con alzado interior rotulado (Altillo, Barra, Balda,
  Cajón 17) y alzado de puertas con diagonales discontinuas; foto del mueble existente.
- **Croquis de reforma (p. ej. dosplanos / GOYA)**: una idea por página, cotas en metros
  (1.56 / 2.64), notas manuscritas del cliente: "¿tirador? ¿uñero? push?", "PENDIENTE",
  "CONCRETAR DISEÑO", "Se reutiliza". Listados de rodapié por estancia.
- **Dossier con páginas giradas (p. ej. BELAGUA)**: texto vertical, rótulos en mayúsculas
  sueltas ("CASCO TEXTIL", "FRENTES BLANCO LAMINADO", "RAL 7043", "CRISTAL AHUMADO"),
  submódulos `A06-1 … A06-6`, cotas en metros.
- **Mediciones / presupuesto del cliente (Presto, cabecera "Código Nat Ud Resumen … CanPres
  PrPres ImpPres")**: cada línea `15.03 A Partida ud PL - PUERTA DE PASO …` es UNA partida
  con su código, descripción larga, cantidad ("Todas 10 10,00") y a veces `DAR PRECIO`,
  `OPCIÓN ROBLE`, `PVP 20 EUROS`. Las CANTIDADES de la medición mandan sobre lo que se
  cuente en los dibujos. Los códigos (PL, PM, A1, M2…) son los mismos que en los planos:
  unificar en UNA sola partida por código, nunca duplicar la del dibujo y la de la medición.

## 2. Códigos de referencia

- `A01`, `A1`, `A06-4`, `A02.1`: armario (o submódulo de armario). `V01`: vestidor.
  `E01`, `E##`: estantería / baldas entre paredes. `M1…M4`: muebles varios (cubrerradiador,
  estantería de comedor, tocador, pasamanos). `P1…P6`, `PL`, `PM`, `PD`, `PC`, `PE`, `r.p1`,
  `PP`: puertas (L = lacada, M = madera, D = doble hoja, C = corredera, E = entrada).
  `D1…D4`, `B1…B4`: dormitorios y baños (NO son muebles: son estancias).
- Un mismo código repetido en varias vistas o páginas (alzado + planta + sección + foto)
  es UNA sola partida.
- Sufijos `-1, -2, .1, .2` tras el código son submódulos del mismo mueble: una partida por
  submódulo solo si tienen medidas y puertas propias; si no, un único armario.

## 3. Unidades y cotas

- Cotas con punto y dos decimales (`2.70`, `0.59`, `1.17`) están en METROS → ×100 para cm.
- Cotas enteras de 2–3 cifras (`219`, `83,5`, `212`) están en CENTÍMETROS.
- Cotas de 4 cifras (`2030`, `725`, `2400`) están en MILÍMETROS → ÷10 para cm.
- "H 212cm", "ALTURA 234cm", "altura especial 270cm", "alto hasta 2,50m" = alto.
- Un rótulo `0.20 TAPETA` o `0.38 MALETERO` encima del armario es una cota de ese
  elemento, no del total. El alto total del armario es la cota vertical completa (p. ej.
  2.70). El ancho total es la cota horizontal inferior completa (p. ej. 3.46 = 1.11+1.11+
  0.55+0.55 módulos; 0.57×6 hojas).
- Si el plano da el ancho de cada hoja (`0.59 0.59`) y el total (`1.17`), las puertas
  miden 59 cm cada una, cantidad = nº de hojas dibujadas.
- "Medidas variables según plano" o "medidas aprox." = tomar la cota dibujada.

## 4. Armarios y vestidores

- **CASCO** = cuerpo/estructura interior ("CASCO TEXTIL" = interior en melamina textil).
  **FRENTES** = puertas ("FRENTES BLANCO LAMINADO" = puertas de melamina blanca).
- **MALETERO** y **ALTILLO** son lo mismo: el módulo superior. La tarifa "Módulo +
  maletero" YA LO INCLUYE en el precio del módulo: no es un extra ni queda pendiente.
- **TAPETA** (0.20 encima del frente) = remate superior hasta el techo; no es puerta.
- **COSTADO VISTO** = lateral del armario visible (extra de tarifa).
- **ESQUINA / RINCONERO** = módulo de esquina (consultar).
- **BARRA** (dibujada como línea con perchas) = barra perchero. **BARRA EN ESQUINA** idem.
- **BALDA** = balda de interior. **BALDA ZAPATERO / BALDAS ZAPATOS / ZAPATERO** = baldas
  (una unidad por balda). **ZAPATERO EXTRAÍBLE** = herraje especial (consultar).
- **CAJÓN 0.20 / Cajón 17** = cajón en cajonera, la cifra es su alto (cm).
  **CAJÓN ACCESORIOS / con celdillas** = cajón normal. **BANDEJA EXTRAÍBLE** = bandeja.
- **HUECO TV**, **ESPACIO ABIERTO**, **ESPACIO PARA CAMA PLEGABLE** = hueco sin coste
  propio (la cama abatible es herraje aparte: consultar).
- **"DOBLE" / "272 cm ALTURA (DOBLE)"** en mediciones = armario de doble altura con altillo.
- **Diagonales discontinuas** que convergen hacia el canto del tirador = puerta ABATIBLE
  (lo más habitual). **Flechas horizontales ↔** o rótulo "corredera" = CORREDERA.
- **PUERTAS SIMULADAS** ("puertas simuladas armario entrada") = solo frentes decorativos,
  SIN cuerpo: no presupuestar módulo, solo puertas.
- **SIN FRENTES / abierto / tipo vestidor** = vestidor (sin puertas).
- **"Interior se reutiliza"**, **"REUTILIZADO"**, **"se mantiene"** = NO se presupuesta
  esa parte (precio 0 con nota), nunca precio máximo.
- Alturas sin cota en armarios → se presupuesta a máximos (305 cm) y se indica.

## 5. Puertas de paso

- **Block** = hoja + cerco + tapetas. **Hoja** = la puerta en sí. **Cerco / marco** y
  **premarco**: no son partidas separadas (incluidos en el block). **Tapetas /
  tapajuntas** (lisas, molduradas, "a inglete"): incluidas; un cambio de estilo es nota.
- **Plinto / plintos lacados** = pieza inferior (extra por puerta en tarifa).
- **Pernios**, **manivela roseta**, **manilla**, **Formani**, **cazoleta**: herrajes;
  las manillas NO se presupuestan (nota "manillas no incluidas") salvo que la medición dé
  PVP. **Condena** = cierre de baño (nota).
- **Bisagras ocultas** = EXTRA de herraje sobre la puerta normal (NO convierte la puerta
  en rasomuro). **Resbalón magnético**, **autocierre**: extras.
- **Rasomuro / enrasada / puerta oculta / sin tapetas con cerco de aluminio** = tarifa
  rasomuro. Solo cuando el rótulo se refiere a la PUERTA, no al herraje.
- **Corredera con dedal / uñero** = corredera normal con tirador embutido. **Guía oculta
  / carril oculto / guía Klein** = herraje de la corredera, NO rasomuro.
- **Estándar 203 / "puerta estándar" / "medida estándar"** sin cota = block 2030×725 mm.
  **Suelo a techo** = alto hasta el techo de la estancia (si no se conoce, consultar).
- **Ciega** = sin vidrio. **Vidriada / con vidrio** = extra de vidrio (consultar).
- **Acorazada / blindada / de seguridad** = fuera de tarifa (consultar), aunque se
  rotule como puerta de paso. **Chapado interior de puerta de acceso / forrado** =
  panelado de puerta principal (tarifa de panelados), no puerta nueva.
- **Embocadura** (jamba y tapeta forrando un paso sin puerta) = partida "otro"
  (consultar), con ancho de luz, alto y fondo de jamba.
- **Abatible pantografiada blanca, altura especial 240cm** = puerta de paso abatible,
  labrado pantografiado, laca blanca, alto 240.
- **Doble hoja / 2 hojas** = cantidad de hojas en una misma partida (ancho de cada hoja).
- **Puerta marco de madera + cristal / tipo Crittall / cerramiento acristalado** =
  familia cerramiento (tarifa de puertas de marco de madera).

## 6. Materiales y acabados

- **LAMINADO**, **laminada**, **melamina**, **melamina textil (Cáctus, lino, Graff…)**,
  **melamina stock** → MELAMINA. La melamina nunca lleva labrado: siempre lisa.
- **LACADO / laca / lacada en RAL 9010 / 9003 / 9016 / 9002 / "blanco roto"** → laca
  blanca. **RAL de grises y oscuros (7043, 7016, 9005…)**, **"lacados oscuros"** → laca
  color oscuro. **Colores claros (beige, arena, gris claro…)** → laca color claro.
- **DM / MDF** = soporte del lacado (no es un material de acabado en sí).
- **Chapa de roble barnizada**, **roble**, **roble iroko / Iroite** → roble barnizado.
  **Roble teñido** → roble teñido. **Cerezo / nogal / sapeli / haya** → otro material
  (consultar). **Madera maciza** → consultar salvo que la tarifa lo contemple.
- **Cristal ahumado / vitrina / metálica con cristal** = puerta tipo vitrina (recargo).
  **Tapa de cristal** = extra (consultar).
- **Hidrófugo** (rodapié) = variante hidrófuga (+1 €/ml).

## 7. Labrados (tipo de puerta)

- **Liso / lisa / ciega lisa** = sin labrado.
- **Pantografiado / frente pantografiado / líneas pantografiadas / fresado de líneas** =
  pantografiado (sencillo si son pocas líneas rectas; complejo si es un dibujo).
- **Plafonado / moldura / baquetón / con rehundido / plafón rehundido / "estilo
  provenzal"** = plafonado/moldura. **Pantografiado + plafonado** = combinación.
- **Fresado 3D** = fresado complejo tridimensional.
- **Tirador tipo uñero** = recargo en puertas de armario; no es tirador suelto.

## 8. Rodapiés, baldas y otros

- **Rodapié** se mide por metros lineales; el alto del perfil (7, 9, 10, 12, 15, 20, 25 cm)
  y el tipo (recto / liso, doble dibujo, pecho paloma, fresado 2 rayas, "con moldura")
  salen del rótulo. "Rodapié 25 cm con moldura" supera la tarifa → consultar.
  Si el plano lista estancias por tipo de rodapié, agrupar por tipo y listar estancias.
- **Estantería entre paredes / baldas con herrajes ocultos / hornacina con baldas /
  balda de obra** = familia balda_pared: cantidad = nº de baldas, ancho = ancho del hueco,
  fondo = profundidad, grosor en notas ("grosor 4cm" = 40 mm). "Herraje oculto" es el
  estándar de la tarifa, no un extra. "Iluminación LED vertical" = LED aparte por mueble.
- **Panelado / revestimiento / palillería / friso** = panelado (tarifa por m² o ml).
- **Pasamanos** = por ml. **Cubrerradiador**, **tocador**, **mueble TV**, **librería**,
  **aparador**, **frente de espejo**, **cocina** = mueble_varios (consultar).
- **Mueble de baño / bajo lavabo / columna de baño** = mueble_bano.

## 9. Marcas del cliente que cambian el presupuesto

- **DAR PRECIO** = partida a valorar. **PENDIENTE / CONCRETAR DISEÑO / a elegir** =
  valorar con lo dibujado y anotar "diseño pendiente".
- **OPCIÓN ROBLE / OPCIÓN CEREZO-NOGAL / OPCIÓN DM LACADO** = el cliente pide VARIANTES
  de precio de la misma partida: anotarlas en "notas" como "variantes: roble, cerezo/nogal".
- **PVP 20 EUROS / Estimación** = precio que propone el cliente (anotar, no inventar).
- **INCLUIDO EN MUEBLES DE COCINA / incluido en otra partida** = no presupuestar aquí.
- **Igualando al existente** = acabado a juego con lo que hay (nota), NO significa que se
  reutilice.
