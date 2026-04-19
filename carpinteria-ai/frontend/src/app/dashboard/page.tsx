"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Estimate {
  estimate_id: string;
  cliente_id: string;
  status: string;
  updated_at: string;
  error?: string;
}

export default function DashboardPage() {
  const [estimates, setEstimates] = useState<Estimate[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchEstimates = async () => {
    try {
      const res = await fetch("http://localhost:8000/estimates");
      if (res.ok) {
        const data = await res.json();
        setEstimates(data.estimates || []);
      }
    } catch (err) {
      console.error("Error fetching estimates:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEstimates();
    const interval = setInterval(fetchEstimates, 15000); // Polling cada 15 segundos
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "human_approval_required":
        return <span className="px-3 py-1 text-sm rounded-full bg-yellow-100 text-yellow-800">Pendiente de Revisión</span>;
      case "completed":
      case "sent_to_holded":
        return <span className="px-3 py-1 text-sm rounded-full bg-blue-100 text-blue-800">Enviado</span>;
      case "approved":
        return <span className="px-3 py-1 text-sm rounded-full bg-green-100 text-green-800">Aprobado</span>;
      case "error":
      case "handled_error":
        return <span className="px-3 py-1 text-sm rounded-full bg-red-100 text-red-800">Error</span>;
      case "rejected":
        return <span className="px-3 py-1 text-sm rounded-full bg-red-100 text-red-800">Rechazado</span>;
      default:
        return <span className="px-3 py-1 text-sm rounded-full bg-gray-100 text-gray-800">Procesando</span>;
    }
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return "-";
    const date = new Date(dateString);
    return date.toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Dashboard de Presupuestos</h1>
      </div>

      {loading ? (
        <p className="text-gray-500">Cargando presupuestos...</p>
      ) : estimates.length === 0 ? (
        <div className="bg-white p-8 text-center rounded-lg shadow-sm border border-gray-200">
          <p className="text-gray-500 text-lg">No hay presupuestos registrados en el sistema.</p>
        </div>
      ) : (
        <div className="bg-white shadow-sm border border-gray-200 rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cliente</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Fecha Actualización</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Estado</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Acciones</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {estimates.map((est) => (
                <tr key={est.estimate_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {est.estimate_id.split("-")[0]}...
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {est.cliente_id || "-"}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {formatDate(est.updated_at)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {getStatusBadge(est.status)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {est.status === "human_approval_required" && (
                      <Link 
                        href={`/estimates/${est.estimate_id}`}
                        className="text-indigo-600 hover:text-indigo-900 font-semibold"
                      >
                        Revisar
                      </Link>
                    )}
                    {est.status !== "human_approval_required" && (
                      <Link 
                        href={`/estimates/${est.estimate_id}`}
                        className="text-gray-500 hover:text-gray-700"
                      >
                        Ver Detalle
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
