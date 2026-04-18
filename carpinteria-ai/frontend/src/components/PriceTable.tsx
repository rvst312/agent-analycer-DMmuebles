import React from 'react';

export default function PriceTable() {
  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b">
            <th className="pb-2">Concepto</th>
            <th className="pb-2">Cantidad</th>
            <th className="pb-2">Precio Unit.</th>
            <th className="pb-2">Total</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="py-2" colSpan={4}>No hay datos aún</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
