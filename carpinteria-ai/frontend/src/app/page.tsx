import UploadForm from "@/components/UploadForm";

export default function Home() {
  return (
    <div className="min-h-screen p-8 pb-20 font-[family-name:var(--font-geist-sans)] flex flex-col items-center justify-center">
      <div className="w-full max-w-4xl mx-auto space-y-8">
        <div className="text-center space-y-4">
          <h1 className="text-4xl font-bold tracking-tight">Generador de Presupuestos IA</h1>
          <p className="text-xl text-muted-foreground">
            Sube un plano de carpintería y obtén un presupuesto automático y detallado.
          </p>
        </div>
        
        <UploadForm />
      </div>
    </div>
  );
}
