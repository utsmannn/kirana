# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Embed widget for external websites with visitor-based session management
- Context Guard to restrict AI responses to specific domains
- Web scraping and crawling capabilities for knowledge base
- Internal tools system (hidden from user-facing responses)
- Admin token authentication for all API endpoints

### Changed
- Improved authentication system using admin tokens
- Removed redundant Channels section from Settings page
- Enhanced embed configuration with customizable themes

## [0.1.0] - 2024-01-01

### Added
- Initial release
- FastAPI backend with SvelteKit frontend
- Provider and Channel management system
- Session management with persistent conversations
- Knowledge base with file upload support
- Real-time streaming chat via SSE and WebSocket
- Docker support with multi-stage builds
- Rate limiting and authentication
- Admin web panel
