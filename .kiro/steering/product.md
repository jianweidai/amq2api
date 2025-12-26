# Product Overview

Amazon Q to Claude API Proxy - A proxy service that converts Claude API requests to Amazon Q/CodeWhisperer and Gemini API requests.

## Core Purpose

Provides a Claude API-compatible interface that routes requests to multiple backend providers:
- Amazon Q (CodeWhisperer)
- Google Gemini
- Custom APIs (OpenAI-compatible or Claude-compatible)

## Key Features

- Full Claude API compatibility (`/v1/messages` endpoint)
- Multi-account management with load balancing and weighted selection
- Automatic token refresh with JWT expiration detection
- Account ban detection and auto-disable
- SSE streaming response support
- Prompt caching simulation
- Web admin interface for account management
- Smart routing based on model and account availability

## Target Users

Developers who want to use Claude API clients with Amazon Q, Gemini, or other LLM backends.
