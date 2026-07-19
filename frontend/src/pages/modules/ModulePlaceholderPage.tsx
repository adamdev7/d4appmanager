import { useParams, Link } from "react-router-dom";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ArrowLeft, Construction } from "lucide-react";

const TITLES: Record<string, { title: string; description: string }> = {
  email: {
    title: "Email Automation",
    description: "Build flows, campaigns, and transactional emails powered by Gmail.",
  },
  analytics: {
    title: "Analytics",
    description: "Revenue, engagement, and automation performance dashboards.",
  },
  sms: {
    title: "SMS Notifications",
    description: "Order updates and marketing messages via SMS providers.",
  },
  support: {
    title: "Customer Support Automation",
    description: "Ticket routing, macros, and AI-assisted customer replies.",
  },
};

export function ModulePlaceholderPage() {
  const { slug } = useParams<{ slug: string }>();
  const meta = TITLES[slug ?? ""] ?? {
    title: "App Module",
    description: "This module is being prepared for a future release.",
  };

  return (
    <div className="max-w-2xl mx-auto">
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-content-muted hover:text-content mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to overview
      </Link>
      <Card padding="lg" className="text-center py-12">
        <Construction className="h-12 w-12 text-content-subtle mx-auto mb-4" />
        <CardTitle className="text-xl">{meta.title}</CardTitle>
        <CardDescription className="mt-2 max-w-md mx-auto">{meta.description}</CardDescription>
        <p className="mt-4 text-sm text-content-subtle">
          Backend automation logic will be connected in a future phase. The navigation and module
          structure are ready.
        </p>
        <Link to="/dashboard" className="inline-block mt-8">
          <Button variant="outline">Return to dashboard</Button>
        </Link>
      </Card>
    </div>
  );
}
