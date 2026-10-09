"use client";

/**
 * Editor de la TARIFA paramétrica (tarifa_config.json del backend).
 * Permite subir/bajar precios base y porcentajes sin tocar código:
 * se guarda y se recarga en caliente (el siguiente presupuesto ya usa lo nuevo).
 */
import { useEffect, useRef, useState } from "react";
import { Loader2, Save, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import apiClient from "@/lib/api";

type Json = number | string | null | Json[] | { [k: string]: Json };

const SECCIONES: Record<string, { titulo: string; ayuda: string }> = {
  modulo:              { titulo: "Módulo + maletero (cuerpo de armario)", ayuda: "Precio por módulo. Tramos en mm; porcentajes en decimales (0.20 = +20%, -0.35 = -35%)." },
  puerta_armario:      { titulo: "Puerta de armario",                     ayuda: "Base puerta lisa lacada blanca abatible. Corredera usa su propia tabla de ancho." },
  interiores:          { titulo: "Interiores de armario",                 ayuda: "Precios fijos por unidad (cajones por alto en mm)." },
  balda_pared:         { titulo: "Baldas entre paredes",                  ayuda: "Tabla base por ancho×largo (mm) + % material + % grosor." },
  puerta_paso_normal:  { titulo: "Puerta de paso normal",                 ayuda: "Base block 2030×725×40. Corredera = recargo en decimal (0.5 = +50%)." },
  puerta_paso_rasomuro:{ titulo: "Puerta de paso rasomuro (oculta)",      ayuda: "Base block con cerco de aluminio y bisagra oculta." },
  vestidor:            { titulo: "Vestidor",                              ayuda: "Armario sin puertas + remate por metro lineal." },
};

function setAtPath(obj: Json, path: (string | number)[], value: Json): Json {
  if (path.length === 0) return value;
  const [head, ...rest] = path;
  if (Array.isArray(obj)) {
    const copy = [...obj];
    copy[head as number] = setAtPath(copy[head as number], rest, value);
    return copy;
  }
  const copy = { ...(obj as { [k: string]: Json }) };
  copy[head as string] = setAtPath(copy[head as string], rest, value);
  return copy;
}

function NumInput({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  // Estado local en texto: permite estados intermedios ("-", "0.", vacío) sin
  // convertirlos a 0 en silencio. Acepta coma o punto decimal. Al salir del
  // campo, si el texto no es un número válido, se restaura el último válido.
  const [text, setText] = useState(String(value));
  const lastValid = useRef(value);

  useEffect(() => {
    if (value !== lastValid.current) {
      lastValid.current = value;
      setText(String(value));
    }
  }, [value]);

  const parse = (raw: string): number | null => {
    const n = Number(raw.trim().replace(",", "."));
    return raw.trim() !== "" && Number.isFinite(n) ? n : null;
  };

  return (
    <input
      type="text"
      inputMode="decimal"
      className="w-24 text-sm text-right border border-gray-200 rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-gray-400 bg-white"
      value={text}
      onChange={e => {
        setText(e.target.value);
        const n = parse(e.target.value);
        if (n !== null && n !== lastValid.current) {
          lastValid.current = n;
          onChange(n);
        }
      }}
      onBlur={() => {
        const n = parse(text);
        setText(String(n !== null ? n : lastValid.current));
        if (n !== null && n !== lastValid.current) {
          lastValid.current = n;
          onChange(n);
        }
      }}
    />
  );
}

function Editor({ value, path, onSet }: {
  value: Json;
  path: (string | number)[];
  onSet: (path: (string | number)[], v: Json) => void;
}) {
  if (typeof value === "number") {
    return <NumInput value={value} onChange={n => onSet(path, n)} />;
  }
  if (value === null) {
    return <span className="text-xs text-gray-400 italic">consultar</span>;
  }
  if (typeof value === "string") {
    return <span className="text-xs text-gray-400">{value}</span>;
  }
  if (Array.isArray(value)) {
    // Tramos [limite_mm, pct] → filas "hasta X mm → pct"
    const esTramos = value.every(v => Array.isArray(v) && v.length === 2 && v.every(x => typeof x === "number"));
    if (esTramos) {
      return (
        <div className="space-y-1">
          {value.map((tramo, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
              <span className="w-10 text-right">hasta</span>
              <NumInput value={(tramo as number[])[0]} onChange={n => onSet([...path, i, 0], n)} />
              <span>mm →</span>
              <NumInput value={(tramo as number[])[1]} onChange={n => onSet([...path, i, 1], n)} />
            </div>
          ))}
          <p className="text-[10px] text-gray-300">por encima del último tramo → consultar (pendiente)</p>
        </div>
      );
    }
    // Lista simple de números (p.ej. largo_tramos_mm)
    if (value.every(v => typeof v === "number")) {
      return (
        <div className="flex items-center gap-2">
          {value.map((v, i) => (
            <NumInput key={i} value={v as number} onChange={n => onSet([...path, i], n)} />
          ))}
        </div>
      );
    }
    return null;
  }
  // Objeto → filas etiqueta / editor
  return (
    <div className="space-y-1.5">
      {Object.entries(value).map(([k, v]) => {
        if (k.startsWith("_")) return (
          <p key={k} className="text-[11px] text-gray-400 italic max-w-xl">{String(v)}</p>
        );
        return (
          <div key={k} className="flex items-start gap-3">
            <span className="text-xs text-gray-600 w-44 pt-1.5 shrink-0">{k.replace(/_/g, " ")}</span>
            <Editor value={v} path={[...path, k]} onSet={onSet} />
          </div>
        );
      })}
    </div>
  );
}

export default function TarifaPage() {
  const [cfg, setCfg] = useState<Json | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get("/knowledge/tarifa");
      setCfg(res.data);
      setDirty(false);
    } catch {
      toast.error("No se pudo cargar la tarifa.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const onSet = (path: (string | number)[], v: Json) => {
    setCfg(prev => (prev === null ? prev : setAtPath(prev, path, v)));
    setDirty(true);
  };

  const save = async () => {
    if (!cfg) return;
    setSaving(true);
    try {
      await apiClient.put("/knowledge/tarifa", cfg);
      toast.success("Tarifa guardada. Los nuevos presupuestos ya usan estos precios.");
      setDirty(false);
    } catch (e) {
      toast.error("Error guardando la tarifa.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center py-24">
      <Loader2 className="w-5 h-5 animate-spin text-gray-300" />
    </div>
  );

  const secciones = cfg && typeof cfg === "object" && !Array.isArray(cfg)
    ? Object.entries(cfg).filter(([k]) => !k.startsWith("_"))
    : [];

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-start justify-between gap-4 mb-1">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Tarifa paramétrica</h1>
          <p className="text-xs text-gray-400 mt-1 max-w-2xl">
            Precios base y porcentajes con los que se calculan los presupuestos.
            Los porcentajes van en decimales: <span className="font-mono">0.20</span> = +20%,{" "}
            <span className="font-mono">-0.35</span> = −35%. Las medidas de los tramos están en mm.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={load} disabled={saving} className="gap-1 text-xs border-gray-200">
            <RotateCcw className="w-3 h-3" /> Descartar
          </Button>
          <Button size="sm" onClick={save} disabled={saving || !dirty} className="gap-1 text-xs min-w-[110px]">
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            {saving ? "Guardando…" : dirty ? "Guardar cambios" : "Sin cambios"}
          </Button>
        </div>
      </div>

      <div className="mt-5 space-y-4">
        {secciones.map(([key, val]) => {
          const meta = SECCIONES[key] ?? { titulo: key.replace(/_/g, " "), ayuda: "" };
          return (
            <details key={key} className="bg-white border border-gray-200 rounded-lg overflow-hidden" open={key === "modulo"}>
              <summary className="px-4 py-3 cursor-pointer select-none hover:bg-gray-50">
                <span className="text-sm font-semibold text-gray-800">{meta.titulo}</span>
                {meta.ayuda && <span className="ml-2 text-[11px] text-gray-400">{meta.ayuda}</span>}
              </summary>
              <div className="px-4 pb-4 pt-1 border-t border-gray-100">
                <Editor value={val} path={[key]} onSet={onSet} />
              </div>
            </details>
          );
        })}
      </div>
    </div>
  );
}
