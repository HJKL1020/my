document.addEventListener("DOMContentLoaded", function() {
    const serverStatusIndicator = document.getElementById("server-status-indicator");
    const uptimeDays = document.getElementById("uptime-days");
    const uptimeHours = document.getElementById("uptime-hours");
    const uptimeMinutes = document.getElementById("uptime-minutes");
    const uptimeSeconds = document.getElementById("uptime-seconds");
    const visitorsCount = document.getElementById("visitors-count");
    const botUsersCount = document.getElementById("bot-users-count");
    const botDownloadsCount = document.getElementById("bot-downloads-count");
    const warningMessageElement = document.getElementById("warning-message");
    const warningBox = document.querySelector(".warning-box"); // Get the container

    let serverStartTimeStamp = null;
    let uptimeInterval;

    // Function to update uptime counter
    function updateUptime() {
        if (!serverStartTimeStamp) return;

        const now = Date.now() / 1000; // Current time in seconds
        const uptimeTotalSeconds = Math.floor(now - serverStartTimeStamp);

        if (uptimeTotalSeconds < 0) return; // Avoid negative time if server time is slightly ahead

        const days = Math.floor(uptimeTotalSeconds / (24 * 60 * 60));
        const hours = Math.floor((uptimeTotalSeconds % (24 * 60 * 60)) / (60 * 60));
        const minutes = Math.floor((uptimeTotalSeconds % (60 * 60)) / 60);
        const seconds = Math.floor(uptimeTotalSeconds % 60);

        uptimeDays.textContent = String(days).padStart(2, "0");
        uptimeHours.textContent = String(hours).padStart(2, "0");
        uptimeMinutes.textContent = String(minutes).padStart(2, "0");
        uptimeSeconds.textContent = String(seconds).padStart(2, "0");
    }

    // Function to fetch stats and update the page
    function fetchAndUpdateStats() {
        fetch("/api/stats")
            .then(response => response.json())
            .then(data => {
                // Update stats
                visitorsCount.textContent = data.visitors !== undefined ? data.visitors : "N/A";
                botUsersCount.textContent = data.bot_users !== undefined ? data.bot_users : "N/A";
                botDownloadsCount.textContent = data.bot_downloads !== undefined ? data.bot_downloads : "N/A";

                // Update warning message
                if (warningMessageElement && data.warning_message) {
                    warningMessageElement.textContent = data.warning_message;
                }
                if (warningBox && data.warning_color) {
                    // Assuming color is a valid CSS color name or hex code
                    warningBox.style.borderColor = data.warning_color;
                    warningBox.style.color = data.warning_color; // Optional: change text color too
                }

                // Update server start time and start uptime counter if not already started
                if (data.server_start_timestamp && !serverStartTimeStamp) {
                    serverStartTimeStamp = data.server_start_timestamp;
                    updateUptime(); // Initial update
                    if (uptimeInterval) clearInterval(uptimeInterval); // Clear previous interval if any
                    uptimeInterval = setInterval(updateUptime, 1000); // Update every second
                }

                // Indicate server is running (can be refined later)
                serverStatusIndicator.style.backgroundColor = "#28a745"; // Green

            })
            .catch(error => {
                console.error("Error fetching stats:", error);
                // Indicate error fetching data
                serverStatusIndicator.style.backgroundColor = "#dc3545"; // Red
                visitorsCount.textContent = "Error";
                botUsersCount.textContent = "Error";
                botDownloadsCount.textContent = "Error";
            });
    }

    // Initial fetch
    fetchAndUpdateStats();

    // Fetch stats every 10 seconds (adjust as needed)
    setInterval(fetchAndUpdateStats, 10000);

    // Blinking effect for server status indicator
    setInterval(() => {
        serverStatusIndicator.style.opacity = serverStatusIndicator.style.opacity === "0.5" ? "1" : "0.5";
    }, 700); // Blink speed

});

