# Requirements Document: 筆畫輸入法 (Stroke Input Method)

## Introduction

本專案旨在開發一個適用於 Windows 10 及以上版本（含 Windows 11）的筆畫輸入法（Wubihua / Stroke Input Method）工具。使用者透過五個基本筆畫鍵（橫、豎、撇、點、折）依照正確筆順輸入漢字，系統即時顯示候選字供選擇。以繁體中文為第一優先支援目標，參考傳統筆畫輸入法的設計。系統須具備高穩定性與強健性，能在長時間使用下保持可靠運作，並提供智慧化的候選字推理與排序能力。

The tool will be implemented as a standalone Windows application (system tray + floating input window) using Python, avoiding the complexity of a full TSF IME while still providing a practical and usable stroke input experience. The application must be robust, stable on Windows 10+, and provide strong inference capabilities for efficient character matching.

## Glossary

- **Stroke_Engine**: The core matching engine that maps stroke sequences to candidate characters
- **Input_Window**: The floating GUI window where the user types stroke keys and views candidates
- **Candidate_List**: The ordered list of matching characters/phrases displayed to the user
- **Stroke_Sequence**: An ordered series of stroke codes (1-5) representing the strokes of a character
- **Stroke_Database**: The data store containing character-to-stroke-sequence mappings and metadata
- **Tray_App**: The system tray application that manages the input method lifecycle
- **Output_Module**: The component responsible for delivering selected characters to the target application
- **Wildcard_Key**: A special key (key 6 or designated key) representing "any stroke" for uncertain input
- **Frequency_Ranker**: The component that orders candidates by usage frequency
- **Phrase_Dictionary**: The data store containing common multi-character words and phrases
- **Inference_Engine**: The intelligent matching subsystem within Stroke_Engine that performs fuzzy matching, contextual ranking, and candidate narrowing beyond simple prefix matching
- **Error_Logger**: The component responsible for recording errors, warnings, and diagnostic information to a log file
- **Resource_Monitor**: The component that tracks memory and CPU usage to prevent resource exhaustion during long sessions

## Requirements

### Requirement 1: Stroke Database Construction（筆畫資料庫建構）

**User Story:** As a developer, I want to build a stroke database from open-source data (Make Me a Hanzi), so that the input method has accurate stroke sequences for Traditional Chinese characters.

#### Acceptance Criteria

1. THE Stroke_Database SHALL contain stroke sequences for at least 9000 Traditional Chinese characters sourced from the Make Me a Hanzi dataset
2. WHEN the Make Me a Hanzi data is parsed, THE Stroke_Database SHALL classify each stroke into exactly one of the five basic types: 橫(1), 豎(2), 撇(3), 點(4), 折(5)
3. THE Stroke_Database SHALL store each character entry with the following fields: character, stroke sequence, total stroke count, and usage frequency
4. WHEN a character has both Traditional and Simplified forms, THE Stroke_Database SHALL prioritize the Traditional Chinese form in candidate ordering
5. FOR ALL characters in the Stroke_Database, parsing the stroke data then serializing then parsing again SHALL produce an equivalent stroke sequence (round-trip property)
6. THE Stroke_Database SHALL be serializable to and loadable from a local file for offline use

### Requirement 2: Five-Key Stroke Input（五鍵筆畫輸入）

**User Story:** As a user, I want to type characters using five stroke keys following correct stroke order, so that I can input Traditional Chinese characters efficiently.

#### Acceptance Criteria

1. THE Stroke_Engine SHALL accept exactly five stroke input keys plus one wildcard key, mapped following the macOS Stroke - Traditional layout: Key J = 橫(héng), Key K = 豎(shù), Key L = 撇(piě), Key U = 點/捺(diǎn/nà), Key I = 折(zhé), Key O = 萬用(wildcard)
2. WHEN the user presses a stroke key, THE Stroke_Engine SHALL append the corresponding stroke code to the current Stroke_Sequence
3. WHEN a Stroke_Sequence is entered, THE Stroke_Engine SHALL return characters whose stroke order matches the entered sequence as a prefix, followed by fuzzy-matched candidates with minor stroke deviations
4. WHEN the entered Stroke_Sequence does not match any character exactly, THE Inference_Engine SHALL attempt approximate matching by tolerating up to one stroke substitution and present results with lower ranking than exact matches
5. WHEN the user presses the Backspace key, THE Stroke_Engine SHALL remove the last stroke from the current Stroke_Sequence
6. WHEN the user presses the Escape key, THE Stroke_Engine SHALL clear the entire current Stroke_Sequence

### Requirement 3: Candidate List Display（候選字顯示）

**User Story:** As a user, I want to see a list of matching candidate characters as I type strokes, so that I can quickly find and select the character I need.

#### Acceptance Criteria

1. WHEN the Stroke_Sequence changes, THE Candidate_List SHALL update within 100 milliseconds to reflect matching characters
2. THE Candidate_List SHALL display candidates ordered by the Frequency_Ranker with the most commonly used characters first, with exact prefix matches ranked above fuzzy matches
3. THE Candidate_List SHALL display a maximum of 9 candidates per page, each labeled with a selection number (1-9)
4. WHEN more than 9 candidates match, THE Candidate_List SHALL support page navigation using Page Up and Page Down keys
5. WHEN the user presses a number key (1-9) while the Candidate_List is visible, THE Input_Window SHALL select and output the corresponding candidate character
6. THE Candidate_List SHALL display the current Stroke_Sequence visually using stroke symbols (一丨丿丶乙) alongside the numeric codes

### Requirement 4: Wildcard Stroke Support（萬用筆畫支援）

**User Story:** As a user, I want to use a wildcard key when I am unsure of a specific stroke, so that I can still find the character I need.

#### Acceptance Criteria

1. THE Stroke_Engine SHALL accept Key O as the Wildcard_Key representing any single stroke (matching macOS Stroke - Traditional wildcard key)
2. WHEN the Wildcard_Key is included in a Stroke_Sequence, THE Stroke_Engine SHALL match characters where any of the five stroke types can occupy that position
3. WHEN multiple Wildcard_Keys are used in a single Stroke_Sequence, THE Stroke_Engine SHALL match all valid combinations across all wildcard positions
4. THE Candidate_List SHALL order wildcard-matched results using the same Frequency_Ranker as exact matches

### Requirement 5: Frequency-Based Candidate Ordering（頻率排序）

**User Story:** As a user, I want the most commonly used characters to appear first in the candidate list, so that I can select characters faster.

#### Acceptance Criteria

1. THE Frequency_Ranker SHALL assign a frequency score to each character based on a predefined Traditional Chinese character frequency list
2. WHEN two characters match the same Stroke_Sequence prefix, THE Frequency_Ranker SHALL rank the character with the higher frequency score first
3. WHEN a character has an equal frequency score to another, THE Frequency_Ranker SHALL use total stroke count as a secondary sort key (fewer strokes first)
4. WHEN the user selects a character, THE Frequency_Ranker SHALL increase that character's frequency score for future sessions (user adaptation)
5. WHEN the user has recently selected a character, THE Frequency_Ranker SHALL boost the ranking of contextually related characters (characters commonly paired in words) in subsequent inputs
6. THE Frequency_Ranker SHALL combine static frequency, user adaptation score, and contextual relevance into a composite ranking score

### Requirement 6: Phrase and Word Association（詞組聯想）

**User Story:** As a user, I want the system to suggest common phrases and words after I select a character, so that I can input multi-character words more efficiently.

#### Acceptance Criteria

1. THE Phrase_Dictionary SHALL contain at least 50,000 common Traditional Chinese words and phrases
2. WHEN the user selects a character, THE Candidate_List SHALL display associated phrases starting with that character as secondary suggestions
3. WHEN a phrase suggestion is selected, THE Output_Module SHALL output all characters of the phrase at once
4. THE Phrase_Dictionary SHALL prioritize Traditional Chinese phrases commonly used in Taiwan and Hong Kong

### Requirement 7: Floating Input Window（浮動輸入視窗）

**User Story:** As a user, I want a floating input window that stays on top of other applications, so that I can use the stroke input method across different programs.

#### Acceptance Criteria

1. THE Input_Window SHALL render as an always-on-top, borderless floating window
2. THE Input_Window SHALL be draggable to any position on the screen by the user
3. WHEN the Input_Window loses focus, THE Input_Window SHALL remain visible and retain the current Stroke_Sequence state
4. THE Input_Window SHALL display the current stroke input area, the Candidate_List, and a visual stroke reference guide
5. WHEN the user double-clicks the Tray_App icon, THE Input_Window SHALL toggle between visible and hidden states

### Requirement 8: Character Output to Target Application（字元輸出）

**User Story:** As a user, I want selected characters to be inserted into whatever application I am currently using, so that the input method works across all Windows programs.

#### Acceptance Criteria

1. WHEN the user selects a candidate character, THE Output_Module SHALL simulate keyboard input to type the character into the currently focused application
2. IF the keyboard simulation fails to deliver the character, THEN THE Output_Module SHALL copy the character to the system clipboard and notify the user
3. IF the clipboard fallback also fails, THEN THE Output_Module SHALL log the error via the Error_Logger and display an inline error message in the Input_Window
4. WHEN a character is output, THE Input_Window SHALL clear the current Stroke_Sequence and prepare for the next input
5. THE Output_Module SHALL support outputting characters to standard Windows applications including Notepad, web browsers, and Microsoft Office on both Windows 10 and Windows 11

### Requirement 9: System Tray Integration（系統匣整合）

**User Story:** As a user, I want the input method to run in the system tray, so that it is always accessible without cluttering my desktop.

#### Acceptance Criteria

1. THE Tray_App SHALL display an icon in the Windows system tray on Windows 10 and Windows 11 when running
2. WHEN the user right-clicks the Tray_App icon, THE Tray_App SHALL display a context menu with options: Show/Hide Input Window, Settings, and Exit
3. WHEN the user selects Exit from the context menu, THE Tray_App SHALL gracefully shut down and release all resources
4. WHEN Windows starts, THE Tray_App SHALL optionally launch automatically based on user configuration

### Requirement 10: Stroke Database Parser and Serializer（資料庫解析與序列化）

**User Story:** As a developer, I want to parse the Make Me a Hanzi raw data and serialize it into an optimized format, so that the application loads quickly.

#### Acceptance Criteria

1. WHEN the raw Make Me a Hanzi dictionary.txt is provided, THE Stroke_Database SHALL parse each line into structured character records
2. WHEN the raw Make Me a Hanzi graphics.txt is provided, THE Stroke_Database SHALL extract stroke type sequences from the SVG stroke data
3. THE Stroke_Database SHALL serialize parsed data into a compact binary or JSON format for fast loading
4. THE Stroke_Database SHALL provide a pretty-printer that formats the database back into a human-readable text format
5. FOR ALL valid character records, parsing then pretty-printing then parsing again SHALL produce an equivalent record (round-trip property)
6. IF a malformed line is encountered during parsing, THEN THE Stroke_Database SHALL log a warning with the line number and skip the malformed entry

### Requirement 11: Keyboard Shortcut and Hotkey Support（快捷鍵支援）

**User Story:** As a user, I want to toggle the input method on and off with a global hotkey, so that I can quickly switch between stroke input and normal typing.

#### Acceptance Criteria

1. THE Tray_App SHALL register a configurable global hotkey (default: Ctrl+Shift+S) to toggle the Input_Window visibility
2. WHEN the global hotkey is pressed while the Input_Window is hidden, THE Input_Window SHALL become visible and receive focus
3. WHEN the global hotkey is pressed while the Input_Window is visible, THE Input_Window SHALL hide and return focus to the previous application
4. IF the configured hotkey conflicts with another application, THEN THE Tray_App SHALL display a notification informing the user of the conflict

### Requirement 12: Settings and Configuration（設定與配置）

**User Story:** As a user, I want to configure the input method settings, so that I can customize the behavior to my preferences.

#### Acceptance Criteria

1. THE Tray_App SHALL provide a settings dialog accessible from the system tray context menu
2. THE settings dialog SHALL allow the user to configure: global hotkey, candidate list page size, auto-start on Windows login, and Input_Window opacity
3. WHEN settings are changed, THE Tray_App SHALL persist the configuration to a local settings file
4. WHEN the application starts, THE Tray_App SHALL load the previously saved configuration
5. FOR ALL valid configuration objects, saving then loading SHALL produce an equivalent configuration (round-trip property)


### Requirement 13: Application Robustness and Stability（應用程式強健性與穩定性）

**User Story:** As a user, I want the application to run reliably on my Windows 10 or Windows 11 PC without crashes or resource issues, so that I can depend on it for daily use over long sessions.

#### Acceptance Criteria

1. THE Tray_App SHALL operate continuously for at least 8 hours without memory leaks or degraded performance
2. THE Resource_Monitor SHALL track memory usage and trigger garbage collection when memory consumption exceeds a configurable threshold (default: 200 MB)
3. IF an unhandled exception occurs in any component, THEN THE Tray_App SHALL catch the exception, log it via the Error_Logger, and continue operation without crashing
4. WHEN the Stroke_Database file is missing or corrupted at startup, THE Tray_App SHALL display a user-friendly error message and attempt to rebuild the database from raw source data
5. IF the settings file is corrupted or unreadable, THEN THE Tray_App SHALL fall back to default configuration values and log a warning via the Error_Logger
6. THE Error_Logger SHALL write diagnostic logs to a rotating log file with a maximum size of 10 MB per file and retain the last 3 log files
7. THE Tray_App SHALL be compatible with Windows 10 (version 1903 and later) and Windows 11, handling OS-specific API differences gracefully
8. WHEN the application is closed unexpectedly (e.g., system shutdown or crash), THE Tray_App SHALL persist the current user frequency data to prevent data loss on next startup
9. IF the Stroke_Database loading takes longer than 5 seconds, THEN THE Tray_App SHALL display a loading indicator and remain responsive to user interaction
10. THE Tray_App SHALL release all system resources (global hotkeys, tray icon, window handles) during graceful shutdown

### Requirement 14: Smart Inference and Contextual Matching（智慧推理與上下文匹配）

**User Story:** As a user, I want the input method to intelligently predict and rank characters even when my stroke input is partial or uncertain, so that I can find the right character quickly without memorizing exact stroke orders.

#### Acceptance Criteria

1. WHEN the user enters a partial Stroke_Sequence (fewer than the total strokes of a character), THE Inference_Engine SHALL rank candidates by combining prefix match length, character frequency, and contextual relevance
2. WHEN the user enters a Stroke_Sequence with one incorrect stroke, THE Inference_Engine SHALL include approximate matches with a tolerance of one stroke substitution, ranked below exact matches
3. WHEN the user has selected a character in the current session, THE Inference_Engine SHALL boost candidates that commonly follow the previously selected character in the Phrase_Dictionary
4. THE Inference_Engine SHALL narrow the candidate set progressively with each additional stroke input, reducing the candidate count monotonically for exact prefix matches
5. WHEN fewer than 3 exact prefix matches exist for a Stroke_Sequence, THE Inference_Engine SHALL supplement the Candidate_List with fuzzy matches to maintain a minimum of 3 visible candidates when available
6. THE Inference_Engine SHALL complete all matching and ranking computations within 50 milliseconds for a Stroke_Database of 9000 characters
7. FOR ALL Stroke_Sequences of length N, the exact-match candidate set for length N+1 SHALL be a subset of the exact-match candidate set for length N (monotonic narrowing property)
