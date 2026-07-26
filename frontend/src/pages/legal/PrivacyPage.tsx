import { Link } from "react-router-dom";
import { LegalLayout } from "@/components/layout/LegalLayout";

export function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" lastUpdated="July 26, 2026">
      <section className="space-y-3">
        <h2>1. Who we are</h2>
        <p>
          App Manager is a multi-store Shopify automation platform operated by D4TECH
          (“we”, “us”, or “our”). This Privacy Policy explains how we collect, use,
          store, and share information when you use App Manager, including our website,
          dashboard, and related services (the “Service”).
        </p>
      </section>

      <section className="space-y-3">
        <h2>2. Information we collect</h2>
        <p>Depending on how you use the Service, we may collect:</p>
        <ul>
          <li>
            <strong className="text-content">Account information</strong> — name, email
            address, password (stored in hashed form), and account preferences.
          </li>
          <li>
            <strong className="text-content">Store and commerce data</strong> — Shopify
            store connections, order details, customer emails and names associated with
            orders, fulfillment and tracking information, and related store settings you
            configure.
          </li>
          <li>
            <strong className="text-content">Email and Gmail (Google user) data</strong> —
            when you connect a Google account, we access Google user data through Google
            OAuth, including your Google account email/profile identifiers and Gmail data
            needed for the Service (message metadata, message content, labels/read state,
            and the ability to send mail). This is used for Email Automation and the AI
            Email Assistant.
          </li>
          <li>
            <strong className="text-content">Advertising data</strong> — when you connect
            Meta Ads, campaign and performance metrics used by Analytics and Ads modules
            (such as spend, impressions, and related reporting fields).
          </li>
          <li>
            <strong className="text-content">Tracking and storefront data</strong> —
            shipment tracking numbers, carrier information, and content used to power
            branded tracking experiences for your customers.
          </li>
          <li>
            <strong className="text-content">Usage and device data</strong> — log data,
            IP address, browser type, and similar technical information used for security,
            debugging, and improving the Service.
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2>3. How we use information</h2>
        <p>We use information to:</p>
        <ul>
          <li>Provide, operate, and improve App Manager and its modules</li>
          <li>
            Run Email Automation (order-triggered and transactional emails via your
            connected Gmail accounts)
          </li>
          <li>
            Power the AI Email Assistant (reading relevant mail, generating draft replies
            with AI, and sending messages you approve or enable)
          </li>
          <li>Provide shipment tracking and branded tracking pages</li>
          <li>
            Generate analytics and ads insights (including profitability, ROAS, and
            related reports)
          </li>
          <li>Authenticate users, secure accounts, and prevent abuse</li>
          <li>Send service-related notices (verification, security, and product updates)</li>
          <li>Comply with legal obligations</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2>4. Google user data</h2>
        <p>
          App Manager’s use of information received from Google APIs adheres to the{" "}
          <a
            href="https://developers.google.com/terms/api-services-user-data-policy"
            target="_blank"
            rel="noopener noreferrer"
          >
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements.
        </p>
        <p>
          When you authorize Google access, App Manager may request scopes that allow us
          to:
        </p>
        <ul>
          <li>Identify your Google account (openid, email, profile)</li>
          <li>
            Read and modify Gmail messages as needed to triage customer mail, draft/send
            replies, and update read/handled state (
            <code className="text-content text-sm">gmail.modify</code>)
          </li>
          <li>
            Send email from your connected Gmail account (
            <code className="text-content text-sm">gmail.send</code>)
          </li>
        </ul>
        <p>
          We access, use, store, and share Google user data only to provide and improve
          user-facing features of App Manager that you enable (Email Automation and AI
          Email Assistant). We do not sell Google user data. We do not use Google user
          data for serving advertisements. We do not allow humans to read Google user data
          unless you give us permission, it is necessary for security/compliance, or we
          are required to by law — and then only with limited access controls.
        </p>
        <p>
          You can revoke App Manager’s access at any time in your Google Account
          permissions and/or by disconnecting Gmail in App Manager Settings.
        </p>
      </section>

      <section className="space-y-3">
        <h2>5. AI processing</h2>
        <p>
          Certain features, including the AI Email Assistant and AI-assisted ads or
          reporting tools, send relevant content (such as email text, business rules you
          configure, or performance summaries) to third-party AI providers to generate
          drafts, classifications, or reports. We use this processing only to deliver the
          features you enable. You are responsible for ensuring that your use of customer
          communications and store data with these features complies with applicable law
          and your own privacy notices.
        </p>
      </section>

      <section className="space-y-3">
        <h2>6. How we share information</h2>
        <p>We may share information with:</p>
        <ul>
          <li>
            <strong className="text-content">Service providers</strong> — infrastructure,
            email delivery, AI, and analytics vendors that process data on our behalf
          </li>
          <li>
            <strong className="text-content">Connected platforms</strong> — Shopify,
            Google (Gmail), Meta, and similar integrations you authorize, according to
            their terms and your connection settings
          </li>
          <li>
            <strong className="text-content">Legal and safety</strong> — when required by
            law, or to protect rights, security, and integrity of the Service
          </li>
          <li>
            <strong className="text-content">Business transfers</strong> — in connection
            with a merger, acquisition, or sale of assets, subject to appropriate
            safeguards
          </li>
        </ul>
        <p>
          We do not sell your personal information. Your customers’ data is processed to
          provide the Service to you as a merchant; you remain the controller of that
          customer data.
        </p>
      </section>

      <section className="space-y-3">
        <h2>7. Data retention</h2>
        <p>
          We retain account, store, email, tracking, and analytics data for as long as
          needed to provide the Service and for legitimate business purposes such as
          security, dispute resolution, and legal compliance. You may disconnect
          integrations or request deletion of your account; residual backups may persist
          for a limited period before permanent removal.
        </p>
      </section>

      <section className="space-y-3">
        <h2>8. Security</h2>
        <p>
          We use administrative, technical, and organizational measures designed to
          protect information, including encrypted transport (HTTPS), hashed passwords, and
          access controls. No method of transmission or storage is completely secure; you
          are responsible for safeguarding your credentials and OAuth connections.
        </p>
      </section>

      <section className="space-y-3">
        <h2>9. Your choices and rights</h2>
        <p>Depending on your location, you may have rights to:</p>
        <ul>
          <li>Access, correct, or delete personal information we hold about you</li>
          <li>Disconnect Gmail, Shopify, Meta, or other integrations at any time</li>
          <li>Object to or restrict certain processing</li>
          <li>Export account-related information where technically feasible</li>
        </ul>
        <p>
          To exercise these rights, contact us using the details below. If you are a
          merchant using App Manager, requests from your customers about their data should
          generally be handled by you; we will assist where we act as your processor.
        </p>
      </section>

      <section className="space-y-3">
        <h2>10. International transfers</h2>
        <p>
          We may process and store information in countries other than where you are
          located. Where required, we use appropriate safeguards for cross-border
          transfers.
        </p>
      </section>

      <section className="space-y-3">
        <h2>11. Children’s privacy</h2>
        <p>
          App Manager is intended for business users. We do not knowingly collect personal
          information from children under 16.
        </p>
      </section>

      <section className="space-y-3">
        <h2>12. Changes to this policy</h2>
        <p>
          We may update this Privacy Policy from time to time. We will post the revised
          version on this page and update the “Last updated” date. Continued use of the
          Service after changes become effective constitutes acceptance of the updated
          policy.
        </p>
      </section>

      <section className="space-y-3">
        <h2>13. Contact</h2>
        <p>
          For privacy questions or requests, contact D4TECH regarding App Manager. You can
          also reach us through your account settings or the support channels provided in
          the Service.
        </p>
        <p>
          See also our{" "}
          <Link to="/terms">Terms of Service</Link>.
        </p>
      </section>
    </LegalLayout>
  );
}
