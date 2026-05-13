"use client";

import React, { useEffect, useRef, useState } from "react";
import { Loader2, Plus, Search, X } from "lucide-react";

interface Contact {
  id: string;
  name: string;
}

interface ContactSearchProps {
  contacts: Contact[];
  loading: boolean;
  error: string | null;
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
  onCreateNew?: (initialName: string) => void;
}

export default function ContactSearch({
  contacts,
  loading,
  error,
  value,
  onChange,
  disabled = false,
  onCreateNew,
}: ContactSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = contacts.find((c) => c.id === value) ?? null;

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = query.trim()
    ? contacts.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))
    : contacts;

  const handleSelect = (contact: Contact) => {
    onChange(contact.id);
    setOpen(false);
    setQuery("");
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChange("");
    setQuery("");
    setOpen(false);
  };

  const handleInputFocus = () => {
    if (!disabled) setOpen(true);
  };

  if (error) {
    return <p className="text-sm text-destructive border rounded-md px-3 py-2">{error}</p>;
  }

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger / input */}
      <div
        className={`flex items-center gap-2 border rounded-md px-3 py-2 bg-white text-sm transition-colors ${
          disabled ? "opacity-50 cursor-not-allowed bg-gray-50" : "cursor-text hover:border-gray-400"
        } ${open ? "border-blue-500 ring-1 ring-blue-500" : "border-input"}`}
        onClick={() => {
          if (!disabled) {
            setOpen(true);
            inputRef.current?.focus();
          }
        }}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground flex-shrink-0" />
        ) : (
          <Search className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        )}

        <input
          ref={inputRef}
          type="text"
          className="flex-1 outline-none bg-transparent placeholder:text-muted-foreground min-w-0"
          placeholder={
            loading
              ? "Cargando clientes..."
              : selected
              ? ""
              : "Buscar cliente de Holded..."
          }
          value={open ? query : ""}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={handleInputFocus}
          disabled={disabled || loading}
          autoComplete="off"
        />

        {/* Show selected name when dropdown is closed */}
        {!open && selected && (
          <span className="flex-1 truncate text-gray-900">{selected.name}</span>
        )}

        {/* Clear button */}
        {selected && !open && (
          <button
            type="button"
            onClick={handleClear}
            className="text-gray-400 hover:text-gray-600 flex-shrink-0"
            tabIndex={-1}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}

        {!loading && !selected && (
          <span className="text-xs text-muted-foreground flex-shrink-0">
            {contacts.length > 0 ? `${contacts.length} clientes` : ""}
          </span>
        )}
      </div>

      {/* Dropdown */}
      {open && !loading && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg flex flex-col">
          {/* Botón fijo arriba */}
          {onCreateNew && (
            <button
              type="button"
              className="w-full text-left px-3 py-2.5 text-sm font-medium text-blue-600 hover:bg-blue-50 border-b border-gray-100 flex items-center gap-2 transition-colors shrink-0"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                setOpen(false);
                setQuery("");
                onCreateNew(query.trim());
              }}
            >
              <Plus className="w-4 h-4 shrink-0" />
              {query.trim() ? `Crear "${query.trim()}"` : "Crear nuevo cliente"}
            </button>
          )}

          {/* Lista scrollable */}
          <div className="overflow-y-auto max-h-56">
            {filtered.length === 0 && (
              <div className="px-3 py-4 text-center text-sm text-gray-500">
                {query ? `Sin resultados para "${query}"` : "No hay clientes"}
              </div>
            )}
            {filtered.map((contact) => (
              <button
                key={contact.id}
                type="button"
                className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 transition-colors ${
                  contact.id === value ? "bg-blue-50 font-medium text-blue-700" : "text-gray-900"
                }`}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => handleSelect(contact)}
              >
                {contact.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
