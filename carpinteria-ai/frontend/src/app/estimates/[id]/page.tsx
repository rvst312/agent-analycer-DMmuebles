export default function EstimatePage({ params }: { params: { id: string } }) {
  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6">Cotización #{params.id}</h1>
      <p>Detalles de la cotización procesada.</p>
    </div>
  );
}
