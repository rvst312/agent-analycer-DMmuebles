"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface Estimate {
  estimate_id: string;
  cliente_id: string;
  status: string;
  updated_at: string;
}

export function Notifications() {
  const router = useRouter();

  useEffect(() => {
    const fetchEstimates = async () => {
      try {
        const res = await fetch("http://localhost:8000/estimates");
        if (res.ok) {
          const data = await res.json();
          const estimates: Estimate[] = data.estimates || [];
          
          // Get already notified from localStorage
          const notifiedKey = "notified_estimates";
          const notified: string[] = JSON.parse(localStorage.getItem(notifiedKey) || "[]");
          const updatedNotified = [...notified];

          estimates.forEach(est => {
            if (est.status === "human_approval_required" && !notified.includes(est.estimate_id)) {
              // Notify
              toast.info(`Nuevo presupuesto para revisar`, {
                description: `El presupuesto de ${est.cliente_id || "Cliente"} requiere tu aprobación.`,
                action: {
                  label: "Ver",
                  onClick: () => router.push(`/estimates/${est.estimate_id}`)
                },
                duration: 10000,
              });

              // Mark as notified
              updatedNotified.push(est.estimate_id);
            }
          });

          // Save back to localStorage if changed
          if (updatedNotified.length !== notified.length) {
            localStorage.setItem(notifiedKey, JSON.stringify(updatedNotified));
          }
        }
      } catch (err) {
        console.error("Error fetching estimates for notifications:", err);
      }
    };

    // Initial check
    fetchEstimates();

    // Poll every 10 seconds
    const interval = setInterval(fetchEstimates, 10000);
    return () => clearInterval(interval);
  }, [router]);

  return null; // This component does not render anything visible
}
