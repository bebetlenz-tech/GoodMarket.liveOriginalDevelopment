// Minigames JavaScript - Live Crash Game Only

let currentSession = null;
let userWallet = null;
let gameActive = false;

// Initialize when page loads
document.addEventListener('DOMContentLoaded', async () => {
    console.log('🎮 Minigames page loaded - FREE to play!');
    await checkGameLimits();
    await loadUserStats(); // Load user stats on page load
});

async function checkGameLimits() {
    try {
        // Crash Game is TEMPORARILY DISABLED - skip limit check
        console.log('🔧 Crash Game temporarily disabled');

        // Check Coin Flip limits
        const coinResponse = await fetch('/minigames/api/check-limit/coin_flip');
        const coinData = await coinResponse.json();

        if (coinData.success && coinData.limit_check) {
            const limitInfo = coinData.limit_check;
            const limitText = document.getElementById('limit-coin_flip');
            const playBtn = document.getElementById('play-coin_flip');

            if (limitText) {
                limitText.textContent = `${limitInfo.remaining_plays} plays remaining today`;
            }

            if (playBtn) {
                playBtn.disabled = !limitInfo.can_play;
            }
        }
    } catch (error) {
        console.error('❌ Error checking game limits:', error);
    }
}

// Load user stats (wallet balance, total earned)
async function loadUserStats() {
    try {
        const response = await fetch('/minigames/api/user-stats');
        const data = await response.json();

        if (data.success) {
            userWallet = data.user_wallet;
            const walletBalanceEl = document.getElementById('wallet-balance');
            if (walletBalanceEl) {
                walletBalanceEl.textContent = `${userWallet.toFixed(2)} G$`;
            }

            await updateTotalEarned();
        } else {
            console.error('❌ Failed to load user stats:', data.error);
        }
    } catch (error) {
        console.error('❌ Error loading user stats:', error);
    }
}


// Open Crash Game - Show dashboard first (like G$ Garden)
window.openGame = async function(gameType) {
    if (gameType === 'crash_game') {
        // Show crash game dashboard first (similar to G$ Garden)
        await showCrashGameDashboard();
    } else if (gameType === 'coin_flip') {
        // Placeholder for Coin Flip game opening
        showNotification('Coin Flip game is coming soon!', 'info');
    }
};

// Show Crash Game Dashboard (similar to G$ Garden)
async function showCrashGameDashboard() {
    const gameContent = document.getElementById('gameModal');
    
    // Fetch current balance
    const balanceResponse = await fetch('/minigames/api/balance');
    const balanceData = await balanceResponse.json();
    const availableBalance = balanceData.available_balance || 0;

    // Fetch daily limit
    const limitResponse = await fetch('/minigames/api/check-limit/crash_game');
    const limitData = await limitResponse.json();
    const remainingPlays = limitData.limit_check?.remaining_plays || 20;
    const playsToday = limitData.limit_check?.plays_today || 0;

    // Fetch game history
    const historyResponse = await fetch('/minigames/api/game-logs');
    const historyData = await historyResponse.json();
    const gameLogs = historyData.game_logs || [];
    const withdrawalLogs = historyData.withdrawal_logs || [];

    // Calculate stats
    let totalWins = 0;
    let totalLosses = 0;
    let totalProfit = 0;

    gameLogs.forEach(log => {
        if (log.result === 'WIN') totalWins++;
        else totalLosses++;
        totalProfit += log.profit_loss;
    });

    const totalWithdrawn = withdrawalLogs.reduce((sum, w) => sum + w.amount, 0);
    
    console.log(`📊 Dashboard: ${playsToday} plays today, ${remainingPlays} remaining`);

    gameContent.innerHTML = `
        <div class="modal-content" style="max-width: 1200px;">
            <button class="close-modal" onclick="window.closeGameModal()">✕ Close</button>
            <div id="gameContent" style="padding: 2rem;">
                <h2 style="font-size: 2rem; margin-bottom: 1rem; color: #fbbf24; text-align: center;">🚀 Crash Game Dashboard</h2>
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <span style="background: rgba(99, 102, 241, 0.2); padding: 0.5rem 1.5rem; border-radius: 12px; color: #6366f1; font-weight: 600;">
                        🎮 ${remainingPlays} plays remaining today (${playsToday}/20 used)
                    </span>
                </div>
                
                <!-- Available Balance Display -->
                <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(5, 150, 105, 0.1)); border: 2px solid #10b981; border-radius: 16px; padding: 2rem; margin-bottom: 2rem; text-align: center;">
                    <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7); margin-bottom: 0.5rem;">💰 Your Available Balance</div>
                    <div style="font-size: 3rem; font-weight: 900; color: #10b981;" id="crash-available-balance">${availableBalance.toFixed(2)} G$</div>
                    <div style="font-size: 0.85rem; color: rgba(255,255,255,0.6); margin-top: 0.5rem;">Max 20 G$ per game (5x crash) • ${remainingPlays} plays left today</div>
                    
                    <!-- Withdrawal Button -->
                    <button onclick="withdrawCrashWinnings()" style="margin-top: 1.5rem; padding: 1rem 2rem; background: linear-gradient(135deg, #fbbf24, #f59e0b); color: white; border: none; border-radius: 12px; font-size: 1.1rem; font-weight: 700; cursor: pointer; ${availableBalance < 100 ? 'opacity: 0.5; cursor: not-allowed;' : ''}">
                        💸 Withdraw to Wallet (Min: 100 G$)
                    </button>
                </div>

                <!-- Stats -->
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 2rem;">
                    <div style="background: rgba(16, 185, 129, 0.1); padding: 1rem; border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.3); text-align: center;">
                        <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7);">Total Wins</div>
                        <div style="font-size: 1.8rem; font-weight: 800; color: #10b981;">${totalWins}</div>
                    </div>
                    <div style="background: rgba(239, 68, 68, 0.1); padding: 1rem; border-radius: 12px; border: 1px solid rgba(239, 68, 68, 0.3); text-align: center;">
                        <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7);">Total Losses</div>
                        <div style="font-size: 1.8rem; font-weight: 800; color: #ef4444;">${totalLosses}</div>
                    </div>
                    <div style="background: rgba(251, 191, 36, 0.1); padding: 1rem; border-radius: 12px; border: 1px solid rgba(251, 191, 36, 0.3); text-align: center;">
                        <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7);">Net Profit/Loss</div>
                        <div style="font-size: 1.8rem; font-weight: 800; color: ${totalProfit >= 0 ? '#10b981' : '#ef4444'};">${totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(2)} G$</div>
                    </div>
                </div>

                <!-- Tab Navigation -->
                <div style="display: flex; gap: 1rem; margin-bottom: 2rem; border-bottom: 2px solid rgba(99, 102, 241, 0.2);">
                    <button onclick="showCrashTab('games')" id="crash-tab-games" style="padding: 1rem 1.5rem; background: linear-gradient(135deg, #6366f1, #a855f7); color: white; border: none; border-radius: 8px 8px 0 0; cursor: pointer; font-weight: 600;">
                        🎮 Game History (${gameLogs.length})
                    </button>
                    <button onclick="showCrashTab('withdrawals')" id="crash-tab-withdrawals" style="padding: 1rem 1.5rem; background: rgba(99, 102, 241, 0.2); color: white; border: none; border-radius: 8px 8px 0 0; cursor: pointer; font-weight: 600;">
                        💸 Withdrawal History (${withdrawalLogs.length})
                    </button>
                </div>

                <!-- Game History Tab -->
                <div id="crash-history-tab-games" style="display: block;">
                    <div style="max-height: 300px; overflow-y: auto; margin-bottom: 2rem;">
                        ${gameLogs.length === 0 ? '<p style="text-align: center; color: rgba(255,255,255,0.5); padding: 2rem;">No games played yet</p>' : `
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead>
                                    <tr style="background: rgba(99, 102, 241, 0.1); border-bottom: 2px solid rgba(99, 102, 241, 0.3);">
                                        <th style="padding: 1rem; text-align: left;">Date</th>
                                        <th style="padding: 1rem; text-align: center;">Multiplier</th>
                                        <th style="padding: 1rem; text-align: center;">Result</th>
                                        <th style="padding: 1rem; text-align: right;">Winnings</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${gameLogs.slice(0, 20).map(log => `
                                        <tr style="border-bottom: 1px solid rgba(99, 102, 241, 0.1);">
                                            <td style="padding: 1rem;">${new Date(log.date).toLocaleString()}</td>
                                            <td style="padding: 1rem; text-align: center; font-weight: 700; color: #a855f7;">${log.multiplier}x</td>
                                            <td style="padding: 1rem; text-align: center;">
                                                <span style="padding: 0.25rem 0.75rem; border-radius: 6px; font-weight: 600; background: ${log.result === 'WIN' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}; color: ${log.result === 'WIN' ? '#10b981' : '#ef4444'};">
                                                    ${log.result}
                                                </span>
                                            </td>
                                            <td style="padding: 1rem; text-align: right; font-weight: 700; color: ${log.winnings > 0 ? '#10b981' : '#ef4444'};">
                                                ${log.winnings > 0 ? '+' : ''}${log.winnings.toFixed(2)} G$
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        `}
                    </div>
                </div>

                <!-- Withdrawal History Tab -->
                <div id="crash-history-tab-withdrawals" style="display: none;">
                    <div style="max-height: 300px; overflow-y: auto; margin-bottom: 2rem;">
                        ${withdrawalLogs.length === 0 ? '<p style="text-align: center; color: rgba(255,255,255,0.5); padding: 2rem;">No withdrawals yet</p>' : `
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead>
                                    <tr style="background: rgba(99, 102, 241, 0.1); border-bottom: 2px solid rgba(99, 102, 241, 0.3);">
                                        <th style="padding: 1rem; text-align: left;">Date</th>
                                        <th style="padding: 1rem; text-align: right;">Amount</th>
                                        <th style="padding: 1rem; text-align: center;">Transaction</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${withdrawalLogs.map(w => `
                                        <tr style="border-bottom: 1px solid rgba(99, 102, 241, 0.1);">
                                            <td style="padding: 1rem;">${new Date(w.date).toLocaleString()}</td>
                                            <td style="padding: 1rem; text-align: right; font-weight: 700; color: #ef4444;">-${w.amount.toFixed(2)} G$</td>
                                            <td style="padding: 1rem; text-align: center;">
                                                <a href="https://explorer.celo.org/mainnet/tx/${w.tx_hash}" target="_blank" style="color: #6366f1; text-decoration: none;">
                                                    ${w.tx_hash.substring(0, 10)}...
                                                </a>
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        `}
                    </div>
                </div>

                <!-- Start Game Button -->
                <button onclick="startCrashGame(0)" ${remainingPlays <= 0 ? 'disabled' : ''} style="width: 100%; padding: 1.5rem; background: ${remainingPlays <= 0 ? 'rgba(100, 116, 139, 0.5)' : 'linear-gradient(135deg, #6366f1, #a855f7)'}; color: white; border: none; border-radius: 12px; font-size: 1.3rem; font-weight: 700; cursor: ${remainingPlays <= 0 ? 'not-allowed' : 'pointer'};">
                    ${remainingPlays <= 0 ? '❌ Daily Limit Reached (Come back tomorrow!)' : '🎮 Start Game'}
                </button>
            </div>
        </div>
    `;

    gameContent.style.display = 'flex';
}

// Tab switching for crash game dashboard
window.showCrashTab = function(tab) {
    // Hide all tabs
    document.getElementById('crash-history-tab-games').style.display = 'none';
    document.getElementById('crash-history-tab-withdrawals').style.display = 'none';

    // Reset all tab buttons
    document.getElementById('crash-tab-games').style.background = 'rgba(99, 102, 241, 0.2)';
    document.getElementById('crash-tab-withdrawals').style.background = 'rgba(99, 102, 241, 0.2)';

    // Show selected tab
    document.getElementById('crash-history-tab-' + tab).style.display = 'block';
    document.getElementById('crash-tab-' + tab).style.background = 'linear-gradient(135deg, #6366f1, #a855f7)';
};

// Withdraw crash game winnings
window.withdrawCrashWinnings = async function() {
    try {
        const balanceResponse = await fetch('/minigames/api/balance');
        const balanceData = await balanceResponse.json();
        const availableBalance = balanceData.available_balance || 0;

        if (availableBalance < 100) {
            showNotification('Minimum withdrawal is 100 G$. Keep playing to reach the minimum!', 'error');
            return;
        }

        if (!confirm(`Withdraw ${availableBalance.toFixed(2)} G$ to your wallet?`)) {
            return;
        }

        // Show processing state
        showNotification('⏳ Processing withdrawal...', 'info');

        const response = await fetch('/minigames/api/withdraw-winnings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (data.success) {
            showNotification(`✅ Successfully withdrawn ${availableBalance.toFixed(2)} G$! TX: ${data.tx_hash.substring(0, 10)}...`, 'success');
            
            // Immediately refresh dashboard with updated balance (0)
            await showCrashGameDashboard();
        } else {
            showNotification(data.error || 'Withdrawal failed', 'error');
        }
    } catch (error) {
        console.error('❌ Withdrawal error:', error);
        showNotification('Failed to process withdrawal', 'error');
    }
};

// Removed bet amount modal - game is now free to play

window.closeGameModal = function() {
    document.getElementById('gameModal').style.display = 'none';
    document.getElementById('gameContent').innerHTML = '';
    gameActive = false;
    currentSession = null;
};

// Deposit functionality removed - game is now free to play

// Crash Game Implementation
async function startCrashGame(betAmount) {
    const gameContent = document.getElementById('gameModal');

    gameContent.innerHTML = `
        <div class="modal-content">
            <button class="close-modal" onclick="window.closeGameModal()">✕ Close</button>
            <div id="gameContent">
                <div style="text-align: center; padding: 2rem;">
                    <h2 style="font-size: 2rem; margin-bottom: 1rem; color: #fbbf24;">🚀 Crash Game - FREE!</h2>
                    <p style="color: rgba(255,255,255,0.8); margin-bottom: 1.5rem;">
                        Watch the multiplier rise! Cash out before it crashes to win points!
                    </p>

            <div id="crashGameContainer" style="position: relative; width: 100%; max-width: 600px; height: 400px; margin: 0 auto; background: linear-gradient(135deg, #1e293b, #0f172a); border-radius: 20px; overflow: hidden; border: 2px solid #6366f1;">
                <canvas id="crashCanvas" width="600" height="400"></canvas>

                <div id="crashMultiplier" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 5rem; font-weight: 900; color: #10b981; text-shadow: 0 0 30px rgba(16, 185, 129, 0.8), 0 0 60px rgba(16, 185, 129, 0.4);">
                    1.00x
                </div>

                <div id="crashStatus" style="position: absolute; top: 20px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.7); padding: 0.5rem 1.5rem; border-radius: 12px; font-weight: 600; color: #fbbf24;">
                    🚀 Rising!
                </div>
            </div>

            <div style="margin-top: 2rem; display: flex; gap: 1rem; justify-content: center; align-items: center;">
                <button id="cashOutBtn" onclick="window.cashOut()" style="padding: 1rem 3rem; background: linear-gradient(135deg, #10b981, #059669); color: white; border: none; border-radius: 12px; font-size: 1.2rem; font-weight: 700; cursor: pointer; opacity: 1;">
                    💰 Cash Out
                </button>
                <div id="potentialWin" style="background: rgba(251, 191, 36, 0.2); padding: 1rem 2rem; border-radius: 12px; border: 2px solid #fbbf24;">
                    <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7);">Current Score:</div>
                    <div style="font-size: 1.5rem; font-weight: 800; color: #fbbf24;">1.00x Points</div>
                </div>
            </div>

            </div>
            </div>
        </div>
    `;

    gameContent.style.display = 'flex';

    // Create game session first
    try {
        const response = await fetch('/minigames/api/start-game', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                game_type: 'crash_game',
                bet_amount: betAmount
            })
        });

        const data = await response.json();

        if (data.success) {
            currentSession = data.session_id;
            window.currentBetAmount = betAmount;
            console.log('✅ Game session created:', currentSession);
            
            // Start game animation after session is created
            initCrashGame();
        } else {
            showNotification(data.error || 'Failed to start game', 'error');
            closeGameModal();
        }
    } catch (error) {
        console.error('❌ Error starting game session:', error);
        showNotification('Failed to start game', 'error');
        closeGameModal();
    }
}

let crashMultiplier = 1.00;
let crashTarget = 1.00;
let crashed = false;
let cashedOut = false;
let animationId = null;
let canvas, ctx;
let particles = [];

// Calculate G$ based on multiplier tiers
function calculateReward(multiplier) {
    if (multiplier < 2.0) {
        return 4.0; // 1.1x - 1.9x = 4 G$
    } else if (multiplier < 3.0) {
        return 8.0; // 2.0x - 2.9x = 8 G$
    } else if (multiplier < 4.0) {
        return 12.0; // 3.0x - 3.9x = 12 G$
    } else if (multiplier < 5.0) {
        return 16.0; // 4.0x - 4.9x = 16 G$
    } else {
        return 20.0; // 5.0x = 20 G$ (max)
    }
}

function initCrashGame() {
    canvas = document.getElementById('crashCanvas');
    ctx = canvas.getContext('2d');

    crashMultiplier = 1.00;
    crashed = false;
    cashedOut = false;
    particles = [];

    // Random crash point between 1.20x and 5.00x (maximum 5x)
    crashTarget = 1.20 + Math.random() * 3.80;

    console.log('🎯 Crash target:', crashTarget.toFixed(2) + 'x');

    document.getElementById('crashStatus').textContent = '🚀 Rising!';
    document.getElementById('cashOutBtn').disabled = false;
    document.getElementById('cashOutBtn').style.cursor = 'pointer';
    document.getElementById('cashOutBtn').style.opacity = '1';

    gameActive = true;
    animateCrash();
}

function animateCrash() {
    if (!gameActive || crashed || cashedOut) return;

    // Increase multiplier with variable speed - MUCH SLOWER
    const increment = 0.003 + Math.random() * 0.005; // Very slow increment for better gameplay
    crashMultiplier += increment;

    // Update display
    const multiplierEl = document.getElementById('crashMultiplier');
    if (multiplierEl) {
        multiplierEl.textContent = crashMultiplier.toFixed(2) + 'x';

        // Color changes based on multiplier
        if (crashMultiplier < 2) {
            multiplierEl.style.color = '#10b981';
        } else if (crashMultiplier < 5) {
            multiplierEl.style.color = '#fbbf24';
        } else {
            multiplierEl.style.color = '#ef4444';
        }
    }

    // Update current score display with tier-based reward
    const currentReward = calculateReward(crashMultiplier);
    document.getElementById('potentialWin').innerHTML = `
        <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7);">Potential Win:</div>
        <div style="font-size: 1.5rem; font-weight: 800; color: #fbbf24;">${crashMultiplier.toFixed(2)}x = ${currentReward.toFixed(2)} G$</div>
    `;

    // Draw animated background
    drawCrashAnimation();

    // Check if crashed
    if (crashMultiplier >= crashTarget) {
        crash();
        return;
    }

    animationId = requestAnimationFrame(animateCrash);
}

function drawCrashAnimation() {
    // Clear canvas
    ctx.fillStyle = 'rgba(15, 23, 42, 0.1)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Add particles
    if (Math.random() < 0.3) {
        particles.push({
            x: Math.random() * canvas.width,
            y: canvas.height,
            vx: (Math.random() - 0.5) * 2,
            vy: -2 - Math.random() * 3,
            size: 2 + Math.random() * 4,
            life: 1,
            color: crashMultiplier < 2 ? '#10b981' : crashMultiplier < 5 ? '#fbbf24' : '#ef4444'
        });
    }

    // Update and draw particles
    particles = particles.filter(p => {
        p.x += p.vx;
        p.y += p.vy;
        p.life -= 0.01;

        if (p.life <= 0) return false;

        ctx.globalAlpha = p.life;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();

        return true;
    });

    ctx.globalAlpha = 1;

    // Draw rising line graph
    ctx.strokeStyle = crashMultiplier < 2 ? '#10b981' : crashMultiplier < 5 ? '#fbbf24' : '#ef4444';
    ctx.lineWidth = 3;
    ctx.beginPath();
    const progress = (crashMultiplier - 1) / (crashTarget - 1);
    const graphHeight = canvas.height * 0.7 * progress;
    ctx.moveTo(50, canvas.height - 50);
    ctx.lineTo(canvas.width - 50, canvas.height - 50 - graphHeight);
    ctx.stroke();
}

async function crash() {
    crashed = true;
    gameActive = false;

    if (animationId) {
        cancelAnimationFrame(animationId);
    }

    // Crash explosion effect
    for (let i = 0; i < 100; i++) {
        particles.push({
            x: canvas.width / 2,
            y: canvas.height / 2,
            vx: (Math.random() - 0.5) * 10,
            vy: (Math.random() - 0.5) * 10,
            size: 3 + Math.random() * 5,
            life: 1,
            color: '#ef4444'
        });
    }

    document.getElementById('crashMultiplier').textContent = '💥 CRASHED!';
    document.getElementById('crashMultiplier').style.color = '#ef4444';
    document.getElementById('crashStatus').textContent = '💥 Crashed at ' + crashMultiplier.toFixed(2) + 'x';
    document.getElementById('cashOutBtn').disabled = true;

    // Finish game with 0 score
    setTimeout(async () => await finishGame(0), 2000);
}

window.cashOut = async function() {
    if (crashed || cashedOut || !gameActive) return;

    cashedOut = true;
    gameActive = false;

    if (animationId) {
        cancelAnimationFrame(animationId);
    }

    const finalMultiplier = crashMultiplier;
    
    // TIER-BASED REWARD SYSTEM:
    // 1.1x-1.9x = 4 G$, 2x-2.9x = 8 G$, 3x-3.9x = 12 G$, 4x-4.9x = 16 G$, 5x = 20 G$
    const totalWinnings = calculateReward(finalMultiplier);

    console.log(`💰 GAME WIN CALCULATION (FREE GAME):`);
    console.log(`   Multiplier: ${finalMultiplier.toFixed(2)}x`);
    console.log(`   Total winnings: ${totalWinnings.toFixed(2)} G$`);
    console.log(`   Tier: 1.1-1.9x = 4 G$, 2x-2.9x = 8 G$, 3x-3.9x = 12 G$, 4x-4.9x = 16 G$, 5x = 20 G$`);

    document.getElementById('crashStatus').textContent = '✅ Cashed Out at ' + finalMultiplier.toFixed(2) + 'x!';
    document.getElementById('cashOutBtn').disabled = true;

    showNotification(`Successfully cashed out at ${finalMultiplier.toFixed(2)}x! Won ${totalWinnings.toFixed(2)} G$! 🎉`, 'success');

    // Complete game and return to dashboard with updated balance
    await finishGame(totalWinnings);
};

async function finishGame(score) {
    try {
        const response = await fetch('/minigames/api/complete-game', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSession,
                score: score,
                game_data: {
                    multiplier: crashMultiplier.toFixed(2),
                    crashed: crashed,
                    cashed_out: cashedOut,
                    bet_amount: window.currentBetAmount,
                    total_winnings: score,
                    net_profit: score - (window.currentBetAmount || 0)
                }
            })
        });

        const data = await response.json();

        if (data.success) {
            const winAmount = data.winnings || score;
            const newBalance = data.available_balance || 0;
            const remainingPlays = data.remaining_plays || 0;
            const playsToday = data.plays_today || 0;
            
            console.log(`✅ Game completed! Plays today: ${playsToday}/20, Remaining: ${remainingPlays}`);
            
            showNotification(`${data.message || 'Game complete!'} Plays left today: ${remainingPlays}/20`, 'success');
            
            // Wait 1.5 seconds then auto-return to dashboard with updated balance AND daily limit
            setTimeout(async () => {
                await showCrashGameDashboard(); // Refresh dashboard with new balance and updated limit
            }, 1500);
        } else {
            showNotification(data.error || 'Game completion failed', 'error');
        }
    } catch (error) {
        console.error('❌ Error completing game:', error);
        showNotification('Failed to complete game', 'error');
    }
}

function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    if (!notification) {
        console.error('Notification element not found!');
        return;
    }
    notification.textContent = message;
    notification.style.display = 'block';
    notification.style.background = type === 'success' ? 'rgba(16, 185, 129, 0.95)' :
                                   type === 'error' ? 'rgba(239, 68, 68, 0.95)' :
                                   'rgba(99, 102, 241, 0.95)';

    setTimeout(() => {
        notification.style.display = 'none';
    }, 3000);
}


// Function to fetch Garden Harvest History
async function getGardenHarvestHistory() {
    try {
        const response = await fetch('/minigames/api/garden-harvest-history?limit=1000');
        const data = await response.json();
        
        if (data.success && data.garden_harvests) {
            // Calculate total from garden harvests
            const total = data.garden_harvests.reduce((sum, harvest) => {
                return sum + (parseFloat(harvest.reward_amount) || 0);
            }, 0);
            console.log('Garden Harvest Total:', total);
            return { total };
        }
        
        return { total: 0 };
    } catch (error) {
        console.error('❌ Error fetching garden harvest history:', error);
        return { total: 0 };
    }
}


// Function to calculate and display Total Earned
async function updateTotalEarned() {
    console.log('📊 Fetching total earned from all sources...');

    // Get Learn & Earn history
    const learnEarnResponse = await fetch('/learn-earn/quiz-history?limit=1000');
    const learnEarnData = await learnEarnResponse.json();

    // Get Telegram Task history  
    const telegramResponse = await fetch('/api/daily-task/history?limit=1000');
    const telegramData = await telegramResponse.json();

    // Get Twitter Task history
    const twitterResponse = await fetch('/api/twitter-task/transaction-history?limit=1000');
    const twitterData = await twitterResponse.json();

    // Get Garden harvest history
    const gardenData = await getGardenHarvestHistory();

    console.log('Learn & Earn Data:', learnEarnData);
    console.log('Telegram Task Data:', telegramData);
    console.log('Twitter Task Data:', twitterData);
    console.log('Garden Harvest Data:', gardenData);

    // Calculate totals
    let learnEarnTotal = 0;
    if (learnEarnData.quiz_history && Array.isArray(learnEarnData.quiz_history)) {
        learnEarnTotal = learnEarnData.quiz_history.reduce((sum, quiz) => {
            return sum + (parseFloat(quiz.amount_g$) || 0);
        }, 0);
    }

    let telegramTotal = 0;
    if (telegramData.success && telegramData.transactions) {
        telegramTotal = telegramData.transactions
            .filter(tx => tx.status === 'completed')
            .reduce((sum, tx) => sum + (parseFloat(tx.reward_amount) || 0), 0);
    }

    let twitterTotal = 0;
    if (twitterData.success && twitterData.transactions) {
        twitterTotal = twitterData.transactions
            .filter(tx => tx.status === 'completed')
            .reduce((sum, tx) => sum + (parseFloat(tx.reward_amount) || 0), 0);
    }

    let gardenTotal = gardenData.total || 0;

    console.log('Learn & Earn Total:', learnEarnTotal);
    console.log('Telegram Task Total:', telegramTotal);
    console.log('Twitter Task Total:', twitterTotal);
    console.log('Garden Harvest Total:', gardenTotal);

    const totalEarned = learnEarnTotal + telegramTotal + twitterTotal + gardenTotal;
    console.log('✅ Total Earned Calculated:', totalEarned, 'G$');

    const totalEarnedEl = document.getElementById('total-earned');
    if (totalEarnedEl) {
        totalEarnedEl.textContent = totalEarned.toFixed(2) + ' G$';
    }
}

// Old Game Logs Modal function removed - now integrated in crash game dashboard

// Game Logs Modal - OLD VERSION (kept for reference, not used)
window.openGameLogsModal_OLD = async function() {
    try {
        const response = await fetch('/minigames/api/game-logs');
        const data = await response.json();

        if (!data.success) {
            showNotification('Failed to load game logs', 'error');
            return;
        }

        const logs = data.game_logs || [];

        const modal = document.getElementById('gameModal');
        const content = document.getElementById('gameContent');

        let totalWins = 0;
        let totalLosses = 0;
        let totalProfit = 0;

        logs.forEach(log => {
            if (log.result === 'WIN') totalWins++;
            else totalLosses++;
            totalProfit += log.profit_loss;
        });

        content.innerHTML = `
            <div style="padding: 2rem; max-width: 900px; width: 100%;">
                <h2 style="font-size: 2rem; margin-bottom: 1.5rem; color: #6366f1;">📊 Game Logs & History</h2>

                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 2rem;">
                    <div style="background: rgba(16, 185, 129, 0.1); padding: 1rem; border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.3);">
                        <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7);">Total Wins</div>
                        <div style="font-size: 1.8rem; font-weight: 800; color: #10b981;">${totalWins}</div>
                    </div>
                    <div style="background: rgba(239, 68, 68, 0.1); padding: 1rem; border-radius: 12px; border: 1px solid rgba(239, 68, 68, 0.3);">
                        <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7);">Total Losses</div>
                        <div style="font-size: 1.8rem; font-weight: 800; color: #ef4444;">${totalLosses}</div>
                    </div>
                    <div style="background: rgba(251, 191, 36, 0.1); padding: 1rem; border-radius: 12px; border: 1px solid rgba(251, 191, 36, 0.3);">
                        <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7);">Total Profit/Loss</div>
                        <div style="font-size: 1.8rem; font-weight: 800; color: ${totalProfit >= 0 ? '#10b981' : '#ef4444'};">
                            ${totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(2)} G$
                        </div>
                    </div>
                </div>

                <div style="background: rgba(255,255,255,0.05); border-radius: 12px; padding: 1rem; max-height: 500px; overflow-y: auto;">
                    ${logs.length === 0 ? '<p style="text-align: center; color: rgba(255,255,255,0.6); padding: 2rem;">No games played yet</p>' : `
                        <table style="width: 100%; color: white;">
                            <thead>
                                <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                                    <th style="padding: 0.75rem; text-align: left; font-size: 0.9rem; color: rgba(255,255,255,0.7);">Date</th>
                                    <th style="padding: 0.75rem; text-align: right; font-size: 0.9rem; color: rgba(255,255,255,0.7);">Bet</th>
                                    <th style="padding: 0.75rem; text-align: right; font-size: 0.9rem; color: rgba(255,255,255,0.7);">Multiplier</th>
                                    <th style="padding: 0.75rem; text-align: center; font-size: 0.9rem; color: rgba(255,255,255,0.7);">Result</th>
                                    <th style="padding: 0.75rem; text-align: right; font-size: 0.9rem; color: rgba(255,255,255,0.7);">Profit/Loss</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${logs.map(log => {
                                    const date = new Date(log.date);
                                    const isWin = log.result === 'WIN';
                                    return `
                                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                            <td style="padding: 0.75rem; font-size: 0.85rem;">${date.toLocaleString()}</td>
                                            <td style="padding: 0.75rem; text-align: right; font-size: 0.9rem;">${log.bet_amount} G$</td>
                                            <td style="padding: 0.75rem; text-align: right; font-size: 0.9rem; font-weight: 600; color: ${isWin ? '#10b981' : '#ef4444'};">${log.multiplier}x</td>
                                            <td style="padding: 0.75rem; text-align: center;">
                                                <span style="padding: 0.25rem 0.75rem; border-radius: 6px; font-size: 0.8rem; font-weight: 600; background: ${isWin ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}; color: ${isWin ? '#10b981' : '#ef4444'};">
                                                    ${log.result}
                                                </span>
                                            </td>
                                            <td style="padding: 0.75rem; text-align: right; font-size: 0.9rem; font-weight: 600; color: ${log.profit_loss >= 0 ? '#10b981' : '#ef4444'};">
                                                ${log.profit_loss >= 0 ? '+' : ''}${log.profit_loss.toFixed(2)} G$
                                            </td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    `}
                </div>

                <button onclick="window.closeGameModal()" style="width: 100%; margin-top: 1.5rem; padding: 1rem; background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; border-radius: 12px; font-size: 1rem; font-weight: 600; cursor: pointer;">
                    Close
                </button>
            </div>
        `;

        modal.style.display = 'flex';

    } catch (error) {
        console.error('❌ Error loading game logs:', error);
        showNotification('Failed to load game logs', 'error');
    }
};
