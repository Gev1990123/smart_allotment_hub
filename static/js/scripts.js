// ============================================
// SHARED JAVASCRIPT FOR ALL PAGES
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    // Mark current page as active in navigation
    const currentPath = window.location.pathname;
    document.querySelectorAll('nav a').forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });
});

// ============================================
// AUTHENTICATION
// ============================================

/**
 * Logout the current user
 */
async function logout() {
    try {
        await fetch('/api/auth/logout', {
            method: 'POST',
            credentials: 'include'
        });
        
        window.location.href = '/login';
    } catch (error) {
        console.error('Logout error:', error);
        // Redirect anyway
        window.location.href = '/login';
    }
}

/**
 * Get current user info
 */
async function getCurrentUser() {
    try {
        const response = await fetch('/api/auth/me', {
            credentials: 'include'
        });
        
        if (response.ok) {
            return await response.json();
        }
        return null;
    } catch (error) {
        console.error('Get user error:', error);
        return null;
    }
}


// ============================================
// UTILITY FUNCTIONS
// ============================================

/**
 * Format a timestamp for display
 * @param {string|Date} timestamp - The timestamp to format
 * @returns {string} Formatted time string (e.g., "14:35")
 */
function formatTime(timestamp) {
    return new Date(timestamp).toLocaleTimeString([], {
        hour: '2-digit', 
        minute: '2-digit'
    });
}

/**
 * Calculate time ago from a timestamp
 * @param {string|Date} timestamp - The timestamp
 * @returns {string} Human-readable time ago (e.g., "5m ago", "2h ago")
 */
function timeAgo(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMinutes = Math.floor((now - date) / 60000);
    
    if (diffMinutes < 1) {
        return 'Just now';
    } else if (diffMinutes < 60) {
        return `${diffMinutes}m ago`;
    } else if (diffMinutes < 1440) {
        const hours = Math.floor(diffMinutes / 60);
        return `${hours}h ago`;
    } else {
        return date.toLocaleDateString();
    }
}

/**
 * Navigate to a device's dashboard page
 * @param {string} deviceUid - The device UID
 */
function viewDevice(deviceUid) {
    window.location.href = `/device/${deviceUid}`;
}

/**
 * Navigate to main dashboard with device selected
 * @param {string} deviceUid - The device UID
 */
function viewHistory(deviceUid) {
    window.location.href = `/?device=${deviceUid}`;
}