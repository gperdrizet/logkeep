# LogKeep Refactoring Plan

## Audit Summary (December 2025)

This document outlines findings from a comprehensive codebase audit and the planned refactoring activities to improve code quality, maintainability, and adherence to Python/FastAPI best practices.

## Critical Issues Identified

### 1. Database Session Management in Background Tasks
- **Impact:** Confusion, potential session leaks
- **Files:** `src/services/processor.py`, `src/api/links.py`
- **Status:** ⏳ Pending

### 2. Missing Transaction Rollback on Errors
- **Impact:** Database inconsistency when GitHub updates fail
- **Files:** `src/services/github.py` (update_link_in_journal)
- **Status:** ⏳ Pending

### 3. Bare Exception Handlers
- **Impact:** Hidden errors, difficult debugging
- **Files:** Multiple locations using bare `except:`
- **Status:** ⏳ Pending

## Implementation Priority

### Phase 1: Immediate Fixes (Week 1) ✅ IN PROGRESS
- [ ] Fix bare exception handlers
- [ ] Clean up database session management in background tasks
- [ ] Add centralized configuration management
- [ ] Fix transaction rollback in link editing
- [ ] Extract duplicate histogram calculation logic

### Phase 2: Architecture Improvements (Week 2-4)
- [ ] Create service layer (LinkService, AnalyticsService, etc.)
- [ ] Implement repository pattern
- [ ] Standardize error handling with custom exceptions
- [ ] Add comprehensive type hints
- [ ] Extract business logic from route handlers

### Phase 3: Quality & Testing (Month 2)
- [ ] Add unit tests (pytest)
- [ ] Add integration tests
- [ ] Implement proper logging (lazy % formatting)
- [ ] Add input validation with Pydantic models
- [ ] Use SQLAlchemy MutableList/MutableDict

### Phase 4: Advanced Features (Month 3)
- [ ] Implement clean architecture layers
- [ ] Add caching layer (Redis)
- [ ] Add rate limiting
- [ ] Add monitoring and observability
- [ ] Performance optimizations

## Positive Aspects to Maintain

✅ Good separation of concerns (models, services, utils)
✅ Proper use of SQLAlchemy ORM
✅ Security basics (password hashing, encryption, JWT)
✅ Background task processing
✅ Retry logic for external operations
✅ Logging infrastructure
✅ Docker support
✅ Environment configuration

## Notes

This is a living document. Update status as items are completed.
Each major change should be tested before moving to the next item.
