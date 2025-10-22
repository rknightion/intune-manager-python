# IntuneManager Swift Application - Comprehensive Architecture Analysis

## Executive Summary

IntuneManager is a **macOS-native SwiftUI application** for managing Microsoft Intune devices, applications, groups, and configurations through the Microsoft Graph API. It leverages modern Swift concurrency patterns, SwiftData for local persistence, and MSAL v2 for authentication. The application is structured around a clean layered architecture with comprehensive permission management and error handling.

**Key Statistics:**
- **95 Swift source files**
- **~36,254 total lines of code**
- **Target Platform:** macOS 15.0+
- **Swift Version:** Swift 6 with strict concurrency
- **Key Dependencies:** MSAL, KeychainAccess, SwiftData, SwiftUI

---

## 1. Overall Project Structure

```
IntuneManager/
├── App/                              # Application entry point
│   ├── IntuneManagerApp.swift       # @main, SwiftUI Scene, global singletons
│   ├── UnifiedContentView.swift     # Root content view with split navigation
│   └── SettingsView.swift           # App-wide settings
│
├── Core/                             # Core infrastructure layer
│   ├── Authentication/               # MSAL integration
│   │   ├── AuthManagerV2.swift      # Token management, session lifecycle
│   │   ├── AuthError.swift          # Auth-specific error types
│   │   └── MSALConfiguration.swift
│   ├── DataLayer/                    # Data persistence
│   │   ├── Models/                   # SwiftData @Model types
│   │   │   ├── Device.swift
│   │   │   ├── Application.swift
│   │   │   ├── Assignment.swift
│   │   │   ├── DeviceGroup.swift
│   │   │   ├── ConfigurationProfile.swift
│   │   │   ├── AuditLog.swift
│   │   │   └── [other domain models]
│   │   └── Persistence/
│   │       ├── LocalDataStore.swift  # SwiftData query/mutation interface
│   │       └── CacheManager.swift    # Cache validity tracking
│   ├── Networking/
│   │   ├── GraphAPIClient.swift     # HTTP client actor with batch support
│   │   └── RateLimiter.swift        # Request throttling
│   ├── Security/
│   │   └── CredentialManager.swift  # Configuration storage (UserDefaults)
│   ├── CrossPlatform/
│   │   └── PlatformCompatibility.swift # macOS shims (AppKit helpers)
│   └── UI/
│       ├── Components/
│       ├── FlowLayout.swift
│       ├── Theme.swift
│
├── Services/                         # Business logic orchestrators
│   ├── DeviceService.swift          # Device inventory + actions
│   ├── ApplicationService.swift      # App catalog + metadata
│   ├── GroupService.swift            # Azure AD groups
│   ├── AssignmentService.swift       # Bulk assignment + progress
│   ├── AssignmentImportService.swift # .csv assignment import
│   ├── AssignmentExportService.swift # Assignment backup
│   ├── ConfigurationService.swift    # Profile management
│   ├── AuditLogService.swift        # Activity history
│   ├── PermissionCheckService.swift  # Graph scope validation
│   └── [other domain services]
│
├── Features/                         # Feature modules (UI + ViewModels)
│   ├── Dashboard/                    # Metrics + charts
│   ├── Devices/                      # Device inventory
│   ├── Applications/                 # App catalog
│   ├── BulkAssignment/               # Multi-app assignment workflow
│   ├── Groups/                       # Group browser
│   ├── Configuration/                # Profile management
│   ├── Reports/                      # Analytics + audit logs
│   ├── Settings/                     # App configuration
│   ├── Setup/                        # Initial configuration wizard
│   └── [other features]
│
├── Extensions/                       # View + type extensions
│   └── Color+SystemColors.swift
│
├── Utilities/
│   └── Logger.swift                  # Categorized logging to os.log
│
├── Assets.xcassets                   # App icons, colors, assets
│
├── Info.plist                        # App metadata + URL schemes
└── IntuneManager.entitlements        # Sandbox + keychain entitlements
```

---

## 2. Core Features and Functionality

### 2.1 Authentication & Authorization

**Framework:** Microsoft Authentication Library (MSAL) v2  
**Location:** `IntuneManager/Core/Authentication/`

**Components:**
- **AuthManagerV2**: Main authentication orchestrator
  - Manages MSAL initialization with redirect URI
  - Handles sign-in/sign-out flows with MSAL web UI
  - Implements token refresh timers (proactive refresh before expiry)
  - Tracks `currentUser` (id, displayName, email, tenantId)
  - Publishes `isAuthenticated`, `tokenExpirationDate` for UI binding
  
- **CredentialManager**: Configuration storage
  - Stores non-secret configuration (Client ID, Tenant ID) in UserDefaults
  - Auto-generates default redirect URI from bundle ID
  - Validates configuration before saving
  - Provides `AppConfiguration` struct with computed `authority` URL

**Permission Management:**
- **PermissionCheckService**: Validates Graph API scopes at startup
  - Centrally defined `requiredPermissions` array
  - Each permission includes scope, description, and dependent features
  - Checks token's granted scopes against required scopes
  - Shows permission alert on startup if scopes are missing
  - Users can continue with warnings or view details in Settings

**Keychain Integration:**
- MSAL automatically stores tokens securely in system keychain
- App configured with keychain sharing entitlements for MSAL access
- Sandbox requires explicit keychain access groups

### 2.2 Data Layer & Persistence

**Framework:** SwiftData (Apple's modern persistence layer)  
**Location:** `IntuneManager/Core/DataLayer/`

**Data Models** (all `@Model` SwiftData types, Codable):
- **Device**: Comprehensive device inventory
  - Identity: `id` (unique), `deviceName`, `serialNumber`, `azureADDeviceId`
  - Hardware: `manufacturer`, `model`, `osVersion`, `processorArchitecture`, `physicalMemoryInBytes`
  - Network: `ipAddressV4`, `wiFiMacAddress`, `ethernetMacAddress`
  - Security: `isEncrypted`, `isSupervised`, `jailBroken`, `partnerReportedThreatState`
  - Compliance: `complianceState` (enum: unknown, compliant, noncompliant, conflict, error)
  - Management: `managementState`, `ownership` (enums), `enrollmentType`
  - Relationships: `installedApps`, `assignedGroups`
  - Fields for compliance grace period, malware counts, battery info, etc.

- **Application**: Mobile app + desktop app catalog
  - Identity: `id`, `displayName`, `appType` (enum with 20+ types: iOS, Android, macOS, Windows)
  - Metadata: `publisher`, `developer`, `version`, `appDescription`
  - Publishing: `publishingState`, `isFeatured`
  - Resources: `largeIcon` (MimeContent), URLs (appStore, privacy, info)
  - Platform support computed from `appType` + `applicableDeviceType`
  - Relationships: `assignments`, `installSummary`
  - Settings: `minimumSupportedOperatingSystem`, platform-specific fields

- **Assignment**: Application deployment record
  - Identity: `id`, `applicationId`, `groupId`
  - Intent: `AssignmentIntent` enum (available, required, uninstall, availableWithoutEnrollment)
  - Status: `AssignmentStatus` enum (pending, inProgress, succeeded, failed, completed)
  - Tracking: `createdDate`, `modifiedDate`, `completedDate`, `retryCount`, `batchId`
  - Settings: Encoded `AppAssignmentSettings` (Codable JSON) for Graph API
  - Relationships: `filter` (AssignmentFilter)

- **DeviceGroup**: Azure AD device group representation
  - Identity: `id`, `displayName`
  - Metadata: `description`, `groupType`, `memberCount`
  - Relationships: devices, members

- **ConfigurationProfile**: Intune configuration deployment
  - Identity: `id`, `displayName`
  - Type: `profileType` (settingsCatalog, template, custom)
  - Platform: `targetPlatform` (iOS, Android, macOS, Windows)
  - Lifecycle: `createdDateTime`, `lastModifiedDateTime`, `deploymentStatus`
  - Content: `rawJSON` for settings, `assignments`

- **CacheMetadata**: Cache validity tracking
  - Records last refresh timestamp per entity type
  - Enables staleness checks (30-minute default)

**Persistence Strategy:**
- **LocalDataStore**: Main interface to SwiftData
  - `fetchDevices()`, `replaceDevices()`: Device CRUD with upsert logic
  - `fetchApplications()`, `fetchAssignments()`: Queries
  - `reset()`: Complete data wipe
  - `summary()`: Storage stats
  - Context-aware, handles detached objects gracefully
  
- **CacheManager**: Cache validity
  - `canUseCache(for:)`: Checks if entity is fresh (<30 minutes old)
  - `updateMetadata()`: Records refresh timestamp
  - Enables intelligent prefetch on app launch

---

## 3. SwiftUI Views and UI Components

### 3.1 Main Navigation Structure

**Root: IntuneManagerApp.swift**
- Configures ModelContainer with Device, Application, DeviceGroup, Assignment, CacheMetadata
- Creates global @StateObject singletons: `authManager`, `credentialManager`, `appState`, `permissionService`
- Presents splash screen → configuration wizard → main app or login screen
- Configures window style, toolbar, default size (1200x800)
- Registers menu commands (View, Account, Tools)

**Root Content: UnifiedContentView.swift**
- **split-view layout** for macOS:
  - Sidebar: UnifiedSidebarView (navigation + account info)
  - Detail: NavigationStack with destination views
- Authenticated vs unauthenticated states
- Permission error handling

**Sidebar: UnifiedSidebarView**
- Navigation sections with AppState.Tab enum:
  - Dashboard, Devices, Applications, Groups, Configuration, Reports, Settings
- Account section: Current user info + token expiration
- Actions: Refresh All, Clear Cache
- Keyboard shortcuts integrated

**Login: UnifiedLoginView**
- Splash screen with app branding
- "Sign in with Microsoft" button → AuthManagerV2.signIn()
- Configuration status display
- Error handling with retry logic

### 3.2 Feature Views

**Dashboard** (`Features/Dashboard/Views/DashboardView.swift`)
- Snapshot metrics: Total devices, apps, assignments
- Compliance donut chart (compliant vs noncompliant)
- Platform distribution (iOS, Android, macOS, Windows)
- Assignment trends
- Time range selector (24h, 7d, 30d)

**Devices** (`Features/Devices/`)
- **DeviceListView**: Table with device inventory
  - Filters: compliance, encryption, supervision, ownership, platform, category
  - Search by device name, user, serial number, principal name
  - Row actions: Sync, details panel
  - Batch operations: Sync visible devices
- **Device detail tabs:**
  - Hardware: processor, memory, storage
  - Network: IP, MAC addresses
  - Management: enrollment date, last sync
  - Compliance: state, grace period
  - Security: malware counts, encryption status

**Applications / Bulk Assignment** (`Features/BulkAssignment/`)
- **BulkAssignmentView**: Multi-app assignment workflow
  - App selector (table with filtering)
  - Group picker (multi-select with toggle helpers)
  - Intent selector: Required, Available, Uninstall, AvailableWithoutEnrollment
  - Assignment settings per platform (mandatory, uninstall restrictions, etc.)
  - Platform compatibility warnings
  - Existing assignment preview to avoid duplicates
  - **Progress HUD** during batch submission
  - Retry logic with exponential backoff (up to 3 attempts)
  - Completion summary with success/failure counts

**Groups** (`Features/Groups/`)
- **GroupListView**: Azure AD device groups
  - Search by display name
  - Member count display
  - Selection helper toggles
- **GroupDetailView**: Group members + metadata
- **GroupSelectionView**: Multi-select for assignments

**Configuration** (`Features/Configuration/`)
- **ConfigurationListView**: Profiles by platform + type
  - Filter: platform, profile type (Settings Catalog, templates, custom)
  - Search
- **ConfigurationDetailView**: Profile settings + assignments
- **ConfigurationAssignmentView**: Update assignments
- **ProfileExportView**: Export JSON
- **ProfileValidationView**: Validate mobile config payloads
- **ProfileStatusView**: Deployment stats

**Reports** (`Features/Reports/Views/ReportsView.swift`)
- Assignment KPIs: total, success, failure, in-progress
- Device compliance overview (table by compliance state)
- Top deployed apps (ranked by reach)
- Recent activity: Audit log browser
  - Time range picker
  - Item limit selector
  - Detail sheet per entry
  - Export to JSON

**Settings** (`Features/Settings/`)
- Account: Current user, tenant, sign out
- Configuration: Re-run setup wizard
- Data Management: Cache status, clear local data, export logs
- Appearance: Theme toggle (Light/Dark/System)

**Setup** (`Features/Setup/ConfigurationView.swift`)
- Interactive wizard for MSAL credentials
- Client ID input
- Tenant ID input
- Redirect URI auto-generation with copy button
- Optional: Client secret toggle
- Validation + save to secure storage

### 3.3 Cross-Platform UI Helpers

**PlatformCompatibility.swift**
- Type aliases: `PlatformViewController`, `PlatformImage`, `PlatformColor`, `PlatformApplication`
- View modifiers:
  - `platformNavigationStyle()`: macOS sidebar styling
  - `platformListStyle()`: SidebarListStyle
  - `platformFormStyle()`: Grouped form with 400px min-width
  - `platformGlassBackground()`: Ultralight material with optional corner radius
- Navigation helpers: `PlatformNavigation<Content>` struct
- macOS-specific: Sidebar toggle, file save dialogs, haptic feedback
- Window management via NSApplication API

**PlatformButton**
- macOS-styled button wrapper with primary/secondary styles

**Shared Components**
- `EmptyStateView`: Placeholder for empty lists
- `FlowLayout`: Custom grid layout for flexible wrapping
- `Theme`: Color palette + typography
- `Color+SystemColors`: System color extensions

---

## 4. Services and Business Logic

**Location:** `IntuneManager/Services/`

### 4.1 Core Data Services

**DeviceService** (~200 lines)
- Fetches managed devices from `/deviceManagement/managedDevices`
- Caching with 30-minute staleness
- Search + filtering (OS, compliance, ownership, encryption)
- Device actions:
  - `syncDevice()`: POST `/managedDevices/{id}/syncDevice`
  - `wipeDevice()`: POST with keep-enrollment-data flag
  - `retireDevice()`: POST `/managedDevices/{id}/retire`
  - `restartDevice()`: POST `/rebootNow`
  - `shutdownDevice()`: POST `/shutDown`
- Batch operations: `performBatchSync()` for multiple devices
- Hydration from local store on app launch

**ApplicationService** (~280 lines)
- Fetches apps from `/deviceAppManagement/mobileApps`
- Expands assignments by default
- Platform compatibility inference (20+ app types)
- Filters out testing/placeholder apps (optional)
- Caching strategy
- Search + type filtering

**GroupService** (~240 lines)
- Fetches device security groups from `/groups`
- Filters for device groups (not user/mail)
- Member enumeration on demand
- Search by display name
- Caching

**AssignmentService** (~1,200+ lines - substantial)
- **Bulk assignment orchestration:**
  - `performBulkAssignment()`: Main entry point
  - Validates platform compatibility
  - Detects conflicting assignments (existing deployments)
  - Chunks requests into batches of 20 (Graph limit)
  - Submits via `POST /mobileApps/{id}/assign` with FlexibleAppAssignment payload
  - Tracks progress with `AssignmentProgress` struct
  - Retries failed batches up to 3 times with exponential backoff
  - Rate-limit aware (respects Retry-After header)
  
- **Assignment history:**
  - Persistent log of submitted assignments
  - Status tracking: pending, in-progress, succeeded, failed
  - Error categorization for remediation
  - `assignmentHistory` array persisted in SwiftData
  
- **Settings handling:**
  - Encodes app-specific assignment settings (install without enrollment, uninstall restrictions, etc.)
  - Platform-specific: iOS deployment method, macOS self-service availability, Android managed store
  - Stores as JSON in Assignment model for Graph API submission

- **Progress reporting:**
  - `AssignmentProgress` struct: total, completed, failed, current operation
  - Per-app progress tracking: `AppProgress` with completion percentage
  - UI-bound updates via @Published properties
  - Verification phase after submission

**AssignmentImportService** (~400+ lines)
- Parses CSV files with columns: AppName, GroupName, Intent
- Validates app/group existence before import
- Bulk load from files
- Error reporting per row

**AssignmentExportService** (~150 lines)
- Exports assignment history to JSON + CSV
- Includes metadata: timestamp, status, error messages

**ConfigurationService** (~350 lines)
- Fetches Settings Catalog + template profiles
- Profile filtering by platform
- Assignment management
- Template instantiation

**AuditLogService** (~100 lines)
- Queries `/auditLogs/directoryAudits`
- Filters by activity type + date range
- Used in Reports feature

**PermissionCheckService** (~200 lines)
- Centralized permission validation
- Defines `requiredPermissions` array with scope + feature mapping
- Checks token scopes at startup
- Reports missing scopes to user
- Per-feature permission tracking

**Additional Services:**
- **ProfileValidationService**: Validates mobile config payloads
- **ProfileExportService**: Exports profiles to JSON
- **MobileConfigService**: Converts profiles to .mobileconfig format
- **SyncService**: Coordinates multi-service refresh

### 4.2 Network Layer

**GraphAPIClient** (~300 lines, actor-isolated)
- Generic HTTP methods: `get<T>()`, `post<T, R>()`, `patch<T, R>()`, `delete()`
- Automatically acquires bearer token from AuthManagerV2
- JSON codec configuration (ISO8601 dates)
- **Batch operations:**
  - `batch<T>()`: Submits bulk requests
  - `batchModels()`: Type-safe batch with SwiftData models
  - Splits large batches into rate-limited chunks
  - Respects Graph's 429 rate-limit responses
  
- **Pagination:**
  - `getAllPagesForModels()`: Automatically follows OData $skiptoken
  - Fetches all pages for device/app/group queries
  
- **Error handling:**
  - Decodes Graph error responses
  - Logs with Logger.shared
  - Distinguishes permission (403), rate limit (429), not found (404)
  - Transforms to domain-specific error types

**RateLimiter** (actor-isolated)
- Tracks per-minute Graph API request budget
- Splits large batches to respect throttling
- Implements exponential backoff for retries
- Configurable delays between batch submissions

---

## 5. Data Models in Detail

### 5.1 SwiftData Models

All models are `@Model` (SwiftData), `Codable`, and `Identifiable`.

**Device** (~200 properties)
- Unique identity: `id`
- Device info: name, model, manufacturer, OS, version, serial
- User info: principal name, display name, email, user ID
- Management: enrollment date, last sync, management state, ownership
- Compliance: state, grace period expiration
- Security: encryption, supervision, malware counts, threat state
- Hardware: memory, processor, storage, battery
- Network: IP address, MAC addresses
- Exchange integration: access state, last sync time
- Autopilot: enrollment flag
- MDM specifics: management certificate, lost mode, activation lock bypass
- Relationships: installed apps, assigned groups

**Application** (~100 properties)
- Unique identity: `id`
- Metadata: display name, description, publisher, developer, version
- Publishing: state (available/blocked), featured flag
- Type: Enum with 20+ values (iOS, Android, macOS, Windows variants)
- Resources: icon, URLs (store, privacy, info)
- Installation: minimum OS, command lines (install/uninstall)
- App Store: bundle ID, app Store URL
- VPP: applicable device types
- Relationships: assignments, install summary

**Assignment** (~30 properties + computed graphSettings)
- Unique identity: `id`
- References: application ID/name, group ID/name
- Intent: Enum (available, required, uninstall, availableWithoutEnrollment)
- Status: Enum (pending, inProgress, succeeded, failed, completed)
- Lifecycle: created, modified, completed dates
- Error tracking: message, category, failure timestamp, retry count
- Batch tracking: batchId, priority
- Settings: Encoded JSON for Graph API submission (AppAssignmentSettings)
- Filter: Optional assignment filter reference
- Metadata: createdBy, modifiedBy, scheduledDate

**DeviceGroup** (~15 properties)
- Unique identity: `id`
- Metadata: display name, description, type
- Members: count, member list
- Security: mail-enabled, security group flags

**ConfigurationProfile** (~25 properties)
- Unique identity: `id`
- Metadata: display name, description, version
- Type: Enum (settingsCatalog, template, custom)
- Platform: Enum (iOS, Android, macOS, Windows)
- Lifecycle: created, modified dates
- Deployment: status, assignment count
- Content: rawJSON (settings payload)
- Relationships: assignments

**AuditLog** (~20 properties)
- Unique identity: `id`
- Activity: type, category, result
- Actor: user ID, principal
- Resource: target type, target ID
- Timestamp: activity date/time
- Request/Response: IDs for correlation

**CacheMetadata** (~5 properties)
- Entity type identifier
- Last refresh timestamp
- Record count

### 5.2 Request/Response Types

**AppAssignmentSettings** (~15 variants)
- Base: `@odata.type`, intent, target
- iOS/Android: managed app configuration, VPP options
- macOS: self-service availability, update behavior
- Windows: offline availability, remediation actions
- Mobile config: enrollment profile settings

**FlexibleAppAssignment**
- Dynamic payload builder for Graph assignment API
- Handles platform-specific settings encoding
- Avoids explicit nulls (Graph API requirement)

**BatchRequest / BatchResponse**
- Graph batch operation wrappers
- Request: method, URL, body, headers
- Response: status, body (typed)

**AppAssignment** (Graph response type)
- Assignment metadata from Graph
- Includes intent, target, settings

---

## 6. Authentication and Authorization Deep Dive

### 6.1 Authentication Flow

1. **App Launch**
   - `IntuneManagerApp` creates `AuthManagerV2.shared` singleton
   - `RootScene` task calls `initializeApp()`

2. **Check Configuration**
   - `CredentialManager` loads Client ID + Tenant ID from UserDefaults
   - If missing, show ConfigurationView (setup wizard)

3. **MSAL Initialization** (AuthManagerV2)
   - Constructs MSALAADAuthority from tenant ID
   - Configures MSALPublicClientApplicationConfig:
     - Client ID, redirect URI, authority
     - Claims challenge capability ("CP1")
   - Initializes MSALPublicClientApplication
   - Sets up MSAL logging callbacks

4. **Token Acquisition**
   - **Silent flow first**: `checkCachedAccount()` attempts silent token refresh
     - Queries MSAL accounts from cache
     - Tries to acquire token without user interaction
     - On success, updates `currentUser` and `isAuthenticated`
   
   - **Interactive flow**: User clicks "Sign in with Microsoft"
     - `AuthManagerV2.signIn()` calls `acquireToken(with:)` on MSAL
     - Launches Microsoft web authentication UI
     - User consents to requested scopes
     - Returns token + account info
     - Stores account in MSAL keychain automatically

5. **Token Refresh**
   - Timer-based proactive refresh (before expiry)
   - Tracks `tokenExpirationDate` and broadcasts to UI
   - Automatic retry on refresh failure
   - Clear signals on token acquisition failure

6. **Sign Out**
   - Removes all MSAL accounts
   - Clears `currentUser` and `isAuthenticated`
   - Resets app state and clears local data stores
   - Resets PermissionCheckService state

### 6.2 Permission Validation

**Startup Validation** (PermissionCheckService)
1. After sign-in, `permissionService.checkPermissions()` is called
2. Service decodes access token's `scp` (scopes) claim
3. Compares against `requiredPermissions` array:
   ```swift
   let requiredPermissions: [Permission] = [
       Permission(scope: "DeviceManagementManagedDevices.Read.All", 
                  description: "Read device information", 
                  features: ["Devices"]),
       Permission(scope: "DeviceManagementManagedDevices.ReadWrite.All", 
                  description: "Update device information", 
                  features: ["Devices"]),
       // ... more permissions
   ]
   ```
4. If missing scopes detected:
   - Logs warnings
   - Shows alert with missing permission names
   - Offers "Copy Permission List" for admin review
   - Users can continue with reduced functionality

**Runtime Handling** (AppState)
- Service operations catch permission (403) errors
- `appState.handlePermissionError(operation:resource:)` maps to required scopes
- Shows inline permission alert with shortcut to Settings
- Prevents user from attempting operations without permissions

---

## 7. Platform-Specific Integrations

### 7.1 macOS-Specific Features

**Window Management**
- `windowStyle(.titleBar)`: Full window title bars
- `windowToolbarStyle(.unified())`: Modern unified toolbar
- `defaultSize()`: 1200x800 default window
- Multi-window support: Settings, Assignments Overview

**Menu Commands**
- App menu: About, Reconfigure
- Edit menu: Copy Device Info
- View menu: Refresh, Appearance picker
- Account menu: Sign In/Out, current user info
- Tools menu: Bulk Assignment, Clear Data, Export Logs

**Keyboard Shortcuts**
- ⌘R: Refresh
- ⌘⇧A: Bulk Assignment
- ⌘⇧Q: Sign Out
- ⌘,: Settings
- ⌘⌥,: Reconfigure

**File Management**
- `PlatformFileManager`: Wraps NSSavePanel
- Save dialogs for exports (logs, profiles, assignments)
- Haptic feedback via `PlatformHaptics`

**Sidebar Navigation**
- `NavigationSplitView` with balanced style
- Min/ideal/max widths (200/250/300)
- Column visibility state
- Integrated AppState.Tab selection

**AppKit Integrations**
- `NSApplication.shared.setActivationPolicy(.regular)` on launch
- `NSPasteboard` for clipboard operations
- `NSAlert` for permission warnings
- AppKit file dialogs

### 7.2 macOS Sandbox & Entitlements

**Entitlements** (`IntuneManager.entitlements`)
```xml
<dict>
  <key>com.apple.security.app-sandbox</key>
  <true/>
  <key>com.apple.security.files.user-selected.read-write</key>
  <true/>
  <key>com.apple.security.network.client</key>
  <true/>
  <key>com.apple.security.network.server</key>
  <true/>
  <key>keychain-access-groups</key>
  <array>
    <string>$(AppIdentifierPrefix)com.m7kni.io.IntuneManager</string>
    <string>$(AppIdentifierPrefix)com.microsoft.adalcache</string>
    <string>$(AppIdentifierPrefix)com.microsoft.identity.universalstorage</string>
  </array>
</dict>
```

- Sandbox enabled for security
- User file read-write for exports/imports
- Network client/server for Graph API calls
- Keychain groups for MSAL token storage + Microsoft identity storage

**Info.plist**
- URL scheme: `msauth.com.m7kni.io.IntuneManager://auth` for OAuth redirect
- Bundle identifier: Referenced in redirect URI for authentication redirect

---

## 8. Data Persistence and Caching

### 8.1 Persistence Strategy

**SwiftData Container**
- Initialized with: Device, Application, DeviceGroup, Assignment, CacheMetadata
- Automatic schema versioning
- Transactions with save() semantics

**LocalDataStore Lifecycle**
1. **Hydration (app launch)**: Load all entity types into SwiftData container
2. **In-memory sync**: Services maintain Published @Published collections
3. **Cache validation**: CacheManager checks staleness (30-minute default)
4. **Refresh**: Force-refresh fetches from Graph, updates store, updates in-memory
5. **Reset**: Clear all entities (Settings → Data Management)

**Upsert Logic**
- DeviceService.replaceDevices() fetches existing, compares IDs
- Updates properties if device exists, inserts if new, deletes if no longer present
- Preserves model context relationships

### 8.2 Cache Invalidation

**CacheMetadata Tracking**
- Per-entity type: devices, applications, groups, assignments
- Timestamp of last refresh
- Record count for diagnostics

**Staleness Check**
```swift
if cacheManager.canUseCache(for: .devices) && !forceRefresh {
    let cached = dataStore.fetchDevices()
    if !cached.isEmpty { return cached }  // Use cache
}
// Fetch from API
```

**Manual Override**
- Toolbar refresh buttons pass `forceRefresh: true`
- Force full re-fetch + store update

---

## 9. Configuration Files and Build Settings

### 9.1 Xcode Project Configuration

**Target: IntuneManager (macOS)**
- Deployment target: macOS 15.0
- Swift language version: 6
- Strict concurrency checking: Enabled
- Code signing: Automatic (requires team)
- Capabilities: 
  - Keychain Sharing
  - App Groups: `group.$(PRODUCT_BUNDLE_IDENTIFIER)`
  - App Sandbox (for notarization)
  - Outgoing Connections (Client)

**Build Settings**
- Info.plist location: `IntuneManager/Info.plist`
- Entitlements file: `IntuneManager/IntuneManager.entitlements`

### 9.2 Package Dependencies

Configured via Xcode Package Dependencies (not Package.swift):
1. **MSAL** (`microsoft-authentication-library-for-objc`)
   - Version: 2.5.0+
   - Handles OAuth, token management, keychain integration

2. **KeychainAccess** (optional, not currently used but available)
   - Version: 4.2.2+
   - Alternative keychain API (not needed with MSAL's built-in support)

### 9.3 Configuration at Runtime

**Environment Variable Support**
- `INTUNE_CLIENT_ID`: Override client ID
- `INTUNE_TENANT_ID`: Override tenant ID
- `INTUNE_REDIRECT_URI`: Override redirect URI
- Useful for test environments

**UserDefaults Keys**
- `app.config.clientId`: Client ID
- `app.config.tenantId`: Tenant ID
- `app.config.redirectUri`: Redirect URI
- `app.config.isConfigured`: Flag
- `LOGGING_ENABLED`: Debug logging toggle

---

## 10. Testing Infrastructure

### 10.1 Unit Tests (`IntuneManagerTests/`)

Test files:
- **ApplicationPlatformSupportTests.swift**: App type → platform mapping
- **ApplicationAssignmentFilteringTests.swift**: Filter logic for assignments
- **AppAssignmentTargetTypeDecodingTests.swift**: JSON decoding of assignment targets
- **AuthenticationTests.swift**: Auth flow scenarios
- **CrossPlatformTests.swift**: Platform-specific behavior

**Testing Approach:**
- XCTest framework
- Mirrors source structure
- Tests core business logic (services, models)
- UI tests minimal (focus on data flow)

### 10.2 UI Tests (`IntuneManagerUITests/`)

- Optional: Application launch tests
- Focus on critical user flows

### 10.3 Testing Conventions

- Suffix: `*Tests.swift`
- Location: Mirrors source structure
- Coverage: New features should include tests
- Build: `xcodebuild test -scheme IntuneManager -configuration Debug`

---

## 11. Supported Graph API Endpoints

| Feature | Endpoint | Method | Permissions | Batching |
|---------|----------|--------|-------------|----------|
| List devices | `/deviceManagement/managedDevices` | GET | `Read.All` | Yes (pagination) |
| Device sync | `/deviceManagement/managedDevices/{id}/syncDevice` | POST | `PrivilegedOperations.All` | Yes |
| Device wipe | `/deviceManagement/managedDevices/{id}/wipe` | POST | `PrivilegedOperations.All` | No |
| Device retire | `/deviceManagement/managedDevices/{id}/retire` | POST | `PrivilegedOperations.All` | No |
| List apps | `/deviceAppManagement/mobileApps` | GET | `Read.All` | Yes (pagination) |
| Assign app | `/deviceAppManagement/mobileApps/{id}/assign` | POST | `ReadWrite.All` | Yes (batch) |
| List groups | `/groups` | GET | `Group.Read.All` | Yes (pagination) |
| List profiles | `/deviceManagement/configurationPolicies` | GET | `Configuration.Read.All` | Yes |
| Audit logs | `/auditLogs/directoryAudits` | GET | `AuditLog.Read.All` | Yes (pagination) |

---

## 12. Error Handling and Resilience

### 12.1 Error Types

**AuthError** (Authentication domain)
- `notConfigured`: No credentials provided
- `msalNotInitialized`: MSAL not ready
- `invalidConfiguration(String)`: Invalid auth config
- `signInFailed(Error)`: User auth failed
- `tokenAcquisitionFailed(Error)`: Token refresh failed
- `msalInitializationFailed(Error)`: MSAL setup failed

**CredentialError** (Configuration domain)
- `invalidConfiguration`: Invalid credential format
- `notConfigured`: No config stored
- `saveFailed(Error)`, `clearFailed(Error)`
- `tokenExpired`: Token refresh failed
- `validationFailed`: Config validation failed

**GraphAPI Errors** (Network domain)
- Decoded from Graph error responses
- Maps HTTP 403 → permission error
- Maps HTTP 429 → rate limit error
- Maps HTTP 404 → not found
- Logged with full details

### 12.2 Resilience Patterns

**Rate Limiting**
- RateLimiter tracks per-minute budget
- Respects Retry-After header
- Exponential backoff for retries (1s, 2s, 4s, ...)
- Splits large batches to avoid throttling

**Retry Logic (Assignments)**
- Up to 3 retries per failed batch
- Exponential backoff between retries
- Detailed failure logging
- User-visible progress + completion summary

**Graceful Degradation**
- Permission errors don't crash app
- Users see actionable alerts
- Can continue with reduced functionality
- Offline: Cached data available, network ops fail gracefully

**Error Propagation**
- Services throw/publish errors
- UI captures and displays via alerts
- Logger.shared logs with category hints
- Exportable logs for debugging

---

## 13. Extensibility Points

### 13.1 Adding New Graph Endpoints

**Process:**
1. Define Codable/SwiftData model in `Core/DataLayer/Models/`
2. Add fetch method to appropriate service
3. Call GraphAPIClient methods: `get<T>()`, `post<T, R>()`, `batch<T>()`
4. Update CacheManager with new entity type if needed
5. Add UI feature under `Features/` folder
6. Update PermissionCheckService with required scopes
7. Write unit tests under `IntuneManagerTests/`

### 13.2 Adding New Features

**Module Structure:**
```
Features/NewFeature/
├── Views/
│   ├── NewFeatureView.swift       # Root view
│   ├── DetailView.swift           # Detail panes
│   └── CompactView.swift          # Alternative layouts
├── ViewModels/
│   └── NewFeatureViewModel.swift
└── README.md                       # Feature docs
```

**Integration:**
1. Create feature module
2. Add Tab to AppState enum
3. Register in UnifiedSidebarView navigation
4. Add route in UnifiedContentView.destinationView()
5. Add menu command if needed
6. Add tests

### 13.3 Custom Services

**Pattern:**
```swift
@MainActor
final class NewService: ObservableObject {
    static let shared = NewService()
    @Published var data: [T] = []
    @Published var isLoading = false
    @Published var error: Error?
    
    private let apiClient = GraphAPIClient.shared
    private let dataStore = LocalDataStore.shared
    
    func fetch(forceRefresh: Bool = false) async throws -> [T] {
        // Check cache, fetch from API, update store
    }
}
```

**Lifecycle:**
- Initialize as @MainActor singleton
- Expose @Published properties for UI binding
- Use async/await for background work
- Log with Logger.shared

---

## 14. Documentation

### 14.1 In-Repository Documentation

**`docs/` Directory:**
- **index.md**: User guide overview
- **getting-started.md**: Setup + configuration
- **supported-entities.md**: Feature capabilities
- **architecture.md**: System design (this document's source)
- **api-optimization.md**: Graph API usage, caching, batching
- **development.md**: Power-user workflows, keyboard shortcuts
- **device-support.md**: Platform coverage
- **contributing.md**: Development guidelines
- **faq.md**: Troubleshooting

### 14.2 Code Documentation

**CLAUDE.md** (AI operator guide)
- Architecture overview
- Implementation guardrails
- Testing expectations
- Graph permission management workflow
- macOS UI guidelines

**In-Code Comments**
- MARK: sections for clarity
- Docstring comments on complex methods
- Category hints in Logger calls

---

## 15. Comparison Points for Python Migration

### Key Architectural Principles to Preserve

1. **Layered Architecture**: Auth → Core → Services → UI
2. **Service Orchestration**: DeviceService, ApplicationService, etc. own Graph API calls
3. **Reactive State**: @Published properties enable live UI updates
4. **Cached Persistence**: SwiftData model → LocalDataStore → UI (offline-first)
5. **Permission Validation**: Centralized PermissionCheckService check at startup
6. **Error Handling**: Mapped to user-actionable messages via AppState
7. **Logging**: Categorized with Logger.shared
8. **Concurrency**: Actor-isolated services, @MainActor UI

### Features to Replicate in Python

| Swift Component | Python Equivalent | Purpose |
|-----------------|-------------------|---------|
| AuthManagerV2 | OAuth 2.0 client (Microsoft OIDC) | Token lifecycle |
| CredentialManager | Config/settings manager | Store Client ID, Tenant ID |
| LocalDataStore | SQLite/ORM (SQLAlchemy) | Data persistence |
| GraphAPIClient | HTTP client (httpx/aiohttp) | API communication |
| Services | Service classes | Business logic |
| PermissionCheckService | Scope validator | Permission checks |
| @Published + SwiftUI | State mgmt + UI framework | Reactive UI binding |
| Logger | Python logging | Structured logging |
| SwiftData models | Pydantic/SQLAlchemy models | Data validation/ORM |

### UI Framework Considerations

- **Swift**: SwiftUI + AppKit for macOS
- **Python**: Could use:
  - **Web**: Django/FastAPI + React/Vue (most portable)
  - **Desktop**: PyQt/PySide, PySimpleGUI, Kivy (cross-platform)
  - **CLI**: Click, Typer (command-line alternative)

### Performance Targets

- Initial load: < 2 seconds (current)
- Device list pagination: < 500ms per page
- Bulk assignment: < 30s for 100 apps × 20 groups
- Cache staleness: 30 minutes default
- Batch size: 20 items (Graph limit)

---

## 16. Known Limitations & Future Work

### Current Limitations
- macOS only (in released build)
- Max 999 apps per tenant (Graph pagination limit)
- 30-minute cache staleness hardcoded
- No delta queries (coming: incremental device sync)
- No background refresh tasks

### Planned Enhancements
- Multi-window assignments overview on iOS/iPadOS
- Delta queries for managed devices
- Background sync with badges
- Compliance automation workflows
- Reporting exportable as PDF/Excel
- Dark mode optimizations

---

## Conclusion

IntuneManager is a **well-architected, production-ready macOS application** that demonstrates:

1. **Modern Swift patterns**: Concurrency (async/await, actors), SwiftData, SwiftUI
2. **Enterprise integration**: MSAL v2, Microsoft Graph SDK-less integration
3. **Scalable design**: Layered services, centralized state, reactive UI
4. **Security**: Sandbox + keychain, no stored secrets, MSAL token management
5. **Error resilience**: Rate limiting, retry logic, graceful degradation
6. **User experience**: Responsive UI, offline data, permission guidance

**For Python migration**, the key is preserving this architectural structure while adapting to Python idioms (async, dependency injection, ORM/models). The Graph API integration, service layer design, and permission model are platform-agnostic and translatable.

