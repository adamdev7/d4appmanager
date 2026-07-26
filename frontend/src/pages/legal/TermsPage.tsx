import { Link } from "react-router-dom";
import { LegalLayout } from "@/components/layout/LegalLayout";

export function TermsPage() {
  return (
    <LegalLayout title="Terms of Service" lastUpdated="July 26, 2026">
      <section className="space-y-3">
        <h2>1. Agreement</h2>
        <p>
          These Terms of Service (“Terms”) govern your access to and use of App Manager,
          a multi-store Shopify automation platform operated by D4TECH (“we”, “us”, or
          “our”). By creating an account or using the Service, you agree to these Terms
          and our <Link to="/privacy">Privacy Policy</Link>.
        </p>
      </section>

      <section className="space-y-3">
        <h2>2. The Service</h2>
        <p>
          App Manager helps merchants automate and manage Shopify store operations from
          one workspace. Depending on your plan and configuration, features may include:
        </p>
        <ul>
          <li>
            <strong className="text-content">AI Email Assistant</strong> — Gmail-connected
            drafting and sending of customer replies with AI assistance and business rules
          </li>
          <li>
            <strong className="text-content">Email Automation</strong> — Shopify-triggered
            transactional and operational emails sent through your connected Gmail accounts
          </li>
          <li>
            <strong className="text-content">Tracking</strong> — shipment tracking,
            carrier enrichment, and branded customer-facing tracking experiences
          </li>
          <li>
            <strong className="text-content">Analytics</strong> — store and advertising
            performance insights, including profitability-oriented metrics
          </li>
          <li>
            <strong className="text-content">Ads</strong> — Meta ads reporting, creative
            health, and related insights
          </li>
          <li>
            <strong className="text-content">Upcoming modules</strong> — such as SMS
            notifications and customer support automation, when made available
          </li>
        </ul>
        <p>
          Features may change, and some modules may be marked as coming soon or require
          specific integrations (Shopify, Gmail, Meta, or others) to function.
        </p>
      </section>

      <section className="space-y-3">
        <h2>3. Eligibility and accounts</h2>
        <p>
          You must be able to form a binding contract and use the Service only for
          legitimate business purposes. You are responsible for the accuracy of your
          registration information, safeguarding login credentials, and all activity under
          your account. Notify us promptly of any unauthorized access.
        </p>
      </section>

      <section className="space-y-3">
        <h2>4. Your stores and integrations</h2>
        <p>
          You may connect third-party services such as Shopify, Gmail (Google), and Meta.
          By connecting an integration, you authorize us to access and process data from
          that platform as needed to provide the features you enable. You represent that
          you have all rights and permissions required to connect those accounts and to
          process related customer and business data through App Manager.
        </p>
        <p>
          Your use of third-party platforms remains subject to their own terms and
          policies. We are not responsible for outages, API changes, or actions by those
          providers.
        </p>
      </section>

      <section className="space-y-3">
        <h2>5. Acceptable use</h2>
        <p>You agree not to:</p>
        <ul>
          <li>Use the Service for unlawful, deceptive, or abusive activity</li>
          <li>
            Send spam or unsolicited communications in violation of anti-spam or
            marketing laws
          </li>
          <li>
            Attempt to access accounts, data, or systems you are not authorized to use
          </li>
          <li>
            Reverse engineer, disrupt, or overload the Service, or circumvent security
            controls
          </li>
          <li>
            Use AI features to generate content that infringes rights or violates
            applicable law
          </li>
          <li>
            Misrepresent your identity or affiliation when communicating with customers
            through the Service
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2>6. Customer communications and AI</h2>
        <p>
          When you use Email Automation or the AI Email Assistant, you are responsible for
          the content of messages sent from your connected accounts, including accuracy,
          consent requirements, and compliance with privacy and consumer protection laws.
          AI-generated drafts may be imperfect; you should review outputs before sending
          where appropriate, and you remain responsible for final communications.
        </p>
      </section>

      <section className="space-y-3">
        <h2>7. Your content and data</h2>
        <p>
          You retain ownership of your store data, email content, creatives, and other
          materials you submit (“Customer Content”). You grant us a limited license to
          host, process, transmit, and display Customer Content solely to operate and
          improve the Service for you. Feedback you provide may be used to improve App
          Manager without obligation to you.
        </p>
      </section>

      <section className="space-y-3">
        <h2>8. Our intellectual property</h2>
        <p>
          App Manager, including its software, branding, UI, and documentation, is owned
          by D4TECH and its licensors. These Terms do not grant you any right to copy,
          modify, or redistribute our intellectual property except as needed to use the
          Service.
        </p>
      </section>

      <section className="space-y-3">
        <h2>9. Fees</h2>
        <p>
          If paid plans or usage-based billing apply, pricing, billing cycles, and renewal
          terms will be presented at purchase or in your account. Fees are non-refundable
          except where required by law or expressly stated otherwise. Failure to pay may
          result in suspension or termination of access.
        </p>
      </section>

      <section className="space-y-3">
        <h2>10. Disclaimers</h2>
        <p>
          THE SERVICE IS PROVIDED “AS IS” AND “AS AVAILABLE.” TO THE MAXIMUM EXTENT
          PERMITTED BY LAW, WE DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING
          MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. We do
          not guarantee uninterrupted availability, error-free AI outputs, accurate
          third-party data, or specific business results (including revenue, ROAS, or
          delivery times).
        </p>
      </section>

      <section className="space-y-3">
        <h2>11. Limitation of liability</h2>
        <p>
          TO THE MAXIMUM EXTENT PERMITTED BY LAW, D4TECH AND ITS AFFILIATES WILL NOT BE
          LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR
          FOR LOST PROFITS, REVENUE, DATA, OR BUSINESS OPPORTUNITIES. OUR TOTAL LIABILITY
          ARISING OUT OF OR RELATED TO THE SERVICE WILL NOT EXCEED THE AMOUNTS YOU PAID US
          FOR THE SERVICE IN THE TWELVE (12) MONTHS BEFORE THE CLAIM, OR ONE HUNDRED U.S.
          DOLLARS (US $100) IF YOU HAVE NOT PAID ANY FEES.
        </p>
      </section>

      <section className="space-y-3">
        <h2>12. Indemnification</h2>
        <p>
          You will defend and indemnify D4TECH against claims arising from your use of the
          Service, your Customer Content, your customer communications, or your violation
          of these Terms or applicable law.
        </p>
      </section>

      <section className="space-y-3">
        <h2>13. Suspension and termination</h2>
        <p>
          You may stop using the Service at any time. We may suspend or terminate access
          if you breach these Terms, create risk for the Service or other users, or if
          required by law or a connected platform. Upon termination, your right to use the
          Service ends; provisions that by nature should survive will survive.
        </p>
      </section>

      <section className="space-y-3">
        <h2>14. Changes</h2>
        <p>
          We may update these Terms by posting a revised version and updating the “Last
          updated” date. Continued use after changes take effect constitutes acceptance.
          If you do not agree, you must stop using the Service.
        </p>
      </section>

      <section className="space-y-3">
        <h2>15. Governing law</h2>
        <p>
          These Terms are governed by the laws applicable to D4TECH’s principal place of
          business, without regard to conflict-of-law rules, unless mandatory consumer or
          local law provides otherwise.
        </p>
      </section>

      <section className="space-y-3">
        <h2>16. Contact</h2>
        <p>
          Questions about these Terms can be directed to D4TECH regarding App Manager
          through the support channels available in the Service.
        </p>
        <p>
          See also our <Link to="/privacy">Privacy Policy</Link>.
        </p>
      </section>
    </LegalLayout>
  );
}
