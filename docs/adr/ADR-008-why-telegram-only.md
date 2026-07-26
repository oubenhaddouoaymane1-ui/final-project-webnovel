# ADR-008: Why Telegram is the only user interface

**Status:** Accepted
**Date:** 2026-07-26
**Deciders:** CineOS Architecture Team

## Problem

CineOS needs a user interface through which producers, directors, and artists interact with the pipeline: submitting shots for rendering, approving quality-analyzed renders, reviewing repair results, receiving status notifications, and querying pipeline status. The interface must work across desktop and mobile platforms (team members work from editing bays, on set, and remotely), support file uploads (for reference frames, annotations, and feedback documents), deliver real-time notifications (approval requests, pipeline failures, delivery confirmations), and require zero additional hosting or infrastructure investment beyond what we already maintain. We need to evaluate which interface approach best serves a small, distributed team working on cinematic productions with tight deadlines.

## Decision

Telegram is the sole user interface for all CineOS human interactions. All communication between the system and human users flows through Telegram: the CineOS bot sends status updates, quality analysis reports, approval requests, repair previews, and error notifications. Users interact with the pipeline by sending commands (e.g., /status, /approve, /reject), replying to bot messages with feedback or annotations, uploading reference files (reference frames, style guides, correction notes), and clicking inline keyboard buttons for one-tap approvals and rejections.

The Telegram bot is implemented as a dedicated service that reads from and writes to the PostgreSQL database, receiving pipeline events through database polling or PostgreSQL LISTEN/NOTIFY channels. The bot translates Telegram messages into pipeline actions (approve, reject, request re-render, query status, modify parameters) and translates pipeline events into Telegram messages (status updates, approval requests with render previews, error alerts with diagnostic details). All business logic resides in the database and workflow layer; the bot is a thin presentation layer with no pipeline logic.

## Alternatives Considered

1. **Web UI** — A custom web application providing a full dashboard with pipeline status visualization, render queues, quality analysis reports, and approval workflows. A web UI offers maximum design flexibility, rich data visualization (render comparison views, side-by-side quality scores, timeline visualizations, 3D previews), and the ability to display complex information in interactive layouts. However, building and maintaining a web UI requires frontend engineering expertise (React, CSS, responsive design), a hosting environment (web server, CDN, SSL certificates), authentication and authorization (login, session management, role-based access), and ongoing design and UX work as features are added. A web UI is another service to deploy, monitor, and keep secure against web vulnerabilities (XSS, CSRF, injection). For a small team, the engineering investment in a production-quality web UI is disproportionate to the value delivered over Telegram. Rejected because the development and maintenance cost exceeds the team's capacity and the marginal value over Telegram does not justify the investment.

2. **CLI** — A command-line interface that developers and technical team members use to interact with the pipeline from their terminal. CLIs are powerful for automation, scripting, and integration with development workflows (CI/CD pipelines, cron jobs, shell scripts). They provide precise control, rich output formatting, and composable commands that can be piped and redirected. However, CLIs exclude non-technical team members (producers, directors, some artists) who are not comfortable with terminal interfaces and would need training for every new command. CLIs also do not provide push notifications — users must poll for updates or set up external notification mechanisms (e.g., terminal bell, desktop notifications). Mobile access through a CLI is impractical — there is no reasonable way to run a CLI on a phone or tablet. Rejected because it excludes key stakeholders and lacks notification capabilities.

3. **Mobile app (native)** — A native iOS/Android application designed specifically for CineOS interactions, with custom layouts for pipeline dashboards, render previews, and approval workflows. A native app could provide optimized push notifications, offline access with sync, optimized file upload workflows (camera integration for on-set photo references), and a tailored user experience designed specifically for cinematic production workflows. However, developing and maintaining native mobile apps requires platform-specific expertise (Swift for iOS, Kotlin for Android), app store deployment and review processes (Apple's review can take days), and ongoing compatibility testing across device versions and screen sizes. The development cost of a production-quality mobile app is substantial for a small team — typically six to twelve months for a minimum viable product. Rejected because the development and maintenance cost is prohibitive and Telegram already provides cross-platform mobile access with push notifications.

4. **Email** — Pipeline notifications and approval requests delivered via email. Email is universally accessible, supports file attachments, requires no new application installation, and works on every device with an internet connection. However, email has high latency (minutes to hours for delivery depending on provider and filtering), no real-time interaction model (email is asynchronous and turn-based, not suitable for rapid approve/reject workflows), poor support for inline actions (approval requires replying to an email with specific text, which is error-prone and difficult to parse programmatically), and no rich formatting for quality analysis reports beyond basic HTML. Email is also easily lost in cluttered inboxes and does not support the conversational interaction model that CineOS requires for quick status queries and approvals. Rejected because latency and interaction model are fundamentally incompatible with real-time pipeline operations.

## Trade-offs

We gain zero hosting cost (Telegram's infrastructure handles message delivery, client applications, and media storage), cross-platform access through Telegram's native apps on iOS, Android, Windows, macOS, Linux, and web (web.telegram.org), rich message formatting (Markdown text, inline keyboards with callback buttons, photo and document uploads, location sharing), real-time push notifications that ensure users see approval requests and pipeline alerts immediately regardless of which device they have at hand, a mature and well-documented Bot API with client libraries in every major language, and instant message delivery typically under one second. We accept that Telegram is a third-party dependency (if Telegram changes its Bot API policies, rate limits, or service availability, we must adapt), that message length limits (4096 characters) constrain how much information can be displayed in a single message, that file size limits on bot uploads (50MB for bots sending to users, 20MB for users sending to bots) may constrain the reference files users can send, that some team members may have privacy concerns about using a messaging platform for professional production communication, and that complex visualizations (interactive timelines, side-by-side render comparisons with zoom, 3D previews) are difficult to convey through text and simple images alone.

## Consequences

### Positive
- Zero infrastructure cost for the user interface layer — Telegram provides the hosting, message delivery, client applications, and media handling
- Cross-platform access through Telegram's native apps on iOS, Android, Windows, macOS, Linux, and web with consistent experience across all platforms
- Real-time push notifications ensure users see approval requests and pipeline alerts within seconds, regardless of which device they have at hand
- Inline keyboard buttons provide one-tap approve/reject workflows that are fast, unambiguous, and parseable by the bot without free-text interpretation
- File upload support allows users to send reference frames, style guides, annotations, and other files directly to the bot from any device
- Markdown formatting enables readable quality analysis reports and status updates without building a custom rendering engine
- The Bot API is mature, well-documented, and has active community support with client libraries in Python, TypeScript, Go, Java, and other languages

### Negative
- Telegram is a third-party dependency; API changes, policy updates, rate limit adjustments, or service disruptions directly impact CineOS usability
- Message length limits (4096 characters) require multi-message formatting for complex reports, increasing message count and potentially confusing threading
- File upload size limits (50MB for bots, 20MB for users sending to bots) may constrain large reference files or high-resolution comparison images
- Complex visualizations (interactive timelines, side-by-side render comparisons with zoom and pan, 3D previews) cannot be delivered through Telegram's messaging model
- Some team members may resist using a personal messaging platform for professional production communication, preferring dedicated production tools
- Telegram's message delivery is not guaranteed to be instant in all network conditions, introducing occasional notification latency on slow or unreliable connections
- The bot cannot display complex dashboards or persistent stateful UIs — every interaction is a discrete message exchange with no persistent on-screen state

## Future Improvements
- Implement a Telegram Mini App (web app accessible within Telegram's built-in browser) for complex visualizations that cannot be conveyed through messages alone, such as render comparison sliders and timeline views
- Add message threading to group related pipeline notifications (e.g., all updates for a specific shot in a single reply thread) for cleaner conversation flow
- Implement rich media messages (album uploads for multi-angle render previews, video thumbnails for motion-based quality issues) for richer defect reporting
- Build a Telegram channel for read-only pipeline status broadcasts that do not require individual user interaction, suitable for team-wide status updates
- Add multilingual support for teams working across different languages, using Telegram's built-in localization features
- Implement message persistence and full-text search to allow users to review and find historical pipeline communications
- Add Telegram user role mapping so that different team members see different notification types and approval scopes based on their production role

## References
- Telegram Bot API documentation: https://core.telegram.org/bots/api
- Telegram Bot Features: https://core.telegram.org/bots/features
- Telegram Mini Apps documentation: https://core.telegram.org/bots/webapps
- CineOS Telegram bot implementation: ../src/bot/
- CineOS notification system: ../architecture/notifications.md
