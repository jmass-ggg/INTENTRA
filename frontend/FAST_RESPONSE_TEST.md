# Fast Response Integration Test Plan

## Task 11.4: Fast Response Integration

This document describes how to test the fast response integration in CommunicateView.

## What Was Implemented

1. **Updated `useCommunication` hook**:
   - Added `fast_response_ready` state
   - Added `FAST_RESPONSE_READY`, `FAST_RESPONSE_SELECTED`, and `BYPASS_FAST_RESPONSE` actions
   - Added `checkFastResponse()` function that calls `/communication/fast-response` endpoint

2. **Updated `CommunicateView`**:
   - Imported `FastResponses` component
   - Added UI for testing partner speech input (text input + "Quick Response" button)
   - When partner speech is provided, it calls `checkFastResponse()`
   - If response type is `binary` or `choice`, shows `FastResponses` component
   - If response type is `pipeline`, continues to normal flow
   - Added "Or, build a custom message" button to bypass fast response

## Testing Flow

### 1. Binary Question Test
1. Start the frontend dev server: `npm run dev` (in `aac/frontend`)
2. Start the backend server: `uvicorn app.main:app --reload` (in `aac/backend`)
3. Navigate to `/communicate`
4. In the listener display section, click "Quick Response" on the default statement
   - OR click "+ Add partner speech to check for quick response"
   - Enter a binary question like: "Do you want tea?"
   - Click "Check"
5. **Expected**: FastResponses component should appear with binary options like ["Yes", "No", "A little", "Explain"]
6. Click one of the options
7. **Expected**: The selected option is added as a fragment and generation starts automatically

### 2. Choice Question Test
1. Click "+ Add partner speech to check for quick response"
2. Enter a choice question like: "Would you like tea or coffee?"
3. Click "Check"
4. **Expected**: FastResponses component should appear with choice options like ["Tea", "Coffee", "Neither", "Something else"]
5. Click one of the options
6. **Expected**: Generation starts with the selected choice

### 3. Complex Question (Pipeline) Test
1. Click "+ Add partner speech to check for quick response"
2. Enter a complex question like: "What do you think about the new project timeline?"
3. Click "Check"
4. **Expected**: No FastResponses component appears; user continues to normal flow (intent selector, fragments, etc.)

### 4. Bypass Test
1. Trigger a binary or choice question
2. When FastResponses appears, click "Or, build a custom message"
3. **Expected**: UI returns to idle state, allowing manual message composition

## Backend Endpoint

The backend endpoint `/communication/fast-response` is implemented in `aac/backend/app/main.py`:
- Uses `FastResponseEngine` service
- Returns `{"type": "binary"|"choice"|"pipeline", "options": [...]}`
- Works without LLM (pure pattern matching)

## Requirements Validated

- **16.1**: Fast response engine detects simple question structures
- **16.2**: Simple closed questions return immediate answer choices
- **16.3**: Complex inputs route to full pipeline
- **16.4**: POST endpoint `/communication/fast-response` is called

## UI Elements Added

- "Quick Response" button on partner statement
- "+ Add partner speech to check for quick response" button (for testing)
- FastResponses component display with emerald/green theme
- "Or, build a custom message" bypass button
- Status indicator shows "Quick response available" state
