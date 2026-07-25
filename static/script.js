// Dom Elements
const videoElement = document.getElementById('input-video');
const canvasElement = document.getElementById('output-canvas');
const canvasCtx = canvasElement.getContext('2d');
const startBtn = document.getElementById('start-btn');
const stopBtn = document.getElementById('stop-btn');
const calibrateBtn = document.getElementById('calibrate-btn');
const statusText = document.getElementById('status-text');
const statusLight = document.getElementById('status-light');
const overlayMessage = document.getElementById('overlay-message');
const sensitivityInput = document.getElementById('threshold-slider');
const sensitivityValue = document.getElementById('threshold-value');
const earLeftDisplay = document.getElementById('ear-left');
const earRightDisplay = document.getElementById('ear-right');
const earAvgDisplay = document.getElementById('ear-avg');
const alertnessBar = document.getElementById('alertness-bar');
const alertnessPercent = document.getElementById('alertness-percent');
const photoBtn = document.getElementById('photo-btn');

// HUD Summary Widgets
const logTimeDisplay = document.getElementById('log-time');
const logFocusDisplay = document.getElementById('log-focus');
const logYawnsDisplay = document.getElementById('log-yawns');
const logAlertsDisplay = document.getElementById('log-alerts');

// Challenge Modal elements
const challengeModal = document.getElementById('challenge-modal');
const challengeArea = document.getElementById('challenge-area');
const challengeFeedback = document.getElementById('challenge-feedback');
const startupOverlay = document.getElementById('startup-overlay');
const startupTitle = document.getElementById('startup-title');
const startupDesc = document.getElementById('startup-desc');
const startupStage = document.getElementById('startup-stage');

// Application States
let isMonitoring = false;
let activeSessionId = null;
let camera = null;
let faceMesh = null;
let hands = null;
let audioContext = null;
let oscillator = null;
let gainNode = null;
let alarmPlaying = false;

// Calibration & Sensitivity Defaults
let DROWSINESS_THRESHOLD = parseFloat(localStorage.getItem('drowsinessThreshold')) || 0.12;
sensitivityInput.value = DROWSINESS_THRESHOLD;
sensitivityValue.textContent = DROWSINESS_THRESHOLD.toFixed(2);

const YAWN_THRESHOLD = 0.55;
const TILT_THRESHOLD = 0.35; // head roll angle (warning only)
const PITCH_THRESHOLD_DOWN = 1.35; // head looking down (warning only, never triggers alone)

// --- WAKE-UP CHALLENGE TRIGGER MODEL ---
// The critical challenge is a MICROSLEEP response. It requires sustained eye
// closure as a necessary condition. Head nods, yawns, tilt, looking-down and
// eye-rubbing are warnings only — none of them can fire the challenge on their own.
const WARNING_CLOSED_FRAMES = 3;          // ~0.2s: gentle Level-1 warning after brief closure
const EAR_CLOSED_FRAMES_TO_TRIGGER = 20;  // ~1.3s sustained closure alone -> critical challenge
const EAR_CLOSED_FRAMES_WITH_NOD = 12;    // sustained closure corroborated by a drowsy nod -> fire sooner
const NOD_PITCH_DROP_VELOCITY = 0.12;     // per-frame fall in pitch ratio = loss of muscle control
const NOD_CORROBORATION_WINDOW = 25;      // frames a recent drowsy nod stays "fresh" to corroborate closure

// Tracking counters & metrics
let frameCounter = 0;
let consecutiveDrowsyFrames = 0;   // frames of SUSTAINED EYE CLOSURE (the trigger driver)
let lastPitchRatio = null;         // previous-frame head pitch ratio, for nod velocity
let lastDrowsyNodFrame = -1000;    // last frame a genuine (fast) downward nod was seen

// Session cumulative variables
let sessionStartTime = null;
let elapsedTimerInterval = null;
let elapsedSeconds = 0;
let yawnsCount = 0;
let blinksCount = 0;
let nodsCount = 0;
let alertsCount = 0;
let focusScore = 100;
let alertnessHistory = []; // list of values to average

let isBlinking = false;
let lastYawnFrame = 0;
let lastNodFrame = 0;

// Landmarker structures
let latestHandLandmarks = null;
let latestFaceLandmarks = null;

let startupTiming = {
    pageLoad: performance.now(),
    cameraPermission: null,
    cameraInitialization: null,
    modelLoading: null,
    faceDetectorInitialization: null,
    firstFrameProcessed: null,
    firstFrameReceived: null,
    firstInference: null,
    firstRenderedFrame: null
};
let startupPromise = null;
let monitoringRuntimeReady = false;

// One-shot flags so live-session timing markers only fire on the first real frame
let liveFirstFrameReceivedLogged = false;
let liveFirstInferenceLogged = false;
let liveFirstRenderedFrameLogged = false;

function logStartupStage(stage, detail) {
    const elapsed = performance.now() - startupTiming.pageLoad;
    const label = `[startup] ${stage} after ${Math.round(elapsed)}ms`;
    if (detail) console.info(label, detail);
    else console.info(label);
}

function setStartupOverlay(visible, title = 'Preparing monitoring', description = 'Loading detection models…', stage = 'Initializing') {
    if (!startupOverlay) return;
    if (visible) {
        startupOverlay.classList.remove('hidden');
        if (startupTitle) startupTitle.innerText = title;
        if (startupDesc) startupDesc.innerText = description;
        if (startupStage) startupStage.innerText = stage;
    } else {
        startupOverlay.classList.add('hidden');
    }
}

function createWarmupCanvas() {
    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 480;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#050508';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 44px sans-serif';
    ctx.fillText('Loading...', 180, 250);
    return canvas;
}

async function initializeMonitoringRuntime() {
    if (startupPromise) return startupPromise;

    startupPromise = (async () => {
        logStartupStage('page load', 'Monitoring page initialized');
        setStartupOverlay(true, 'Preparing monitoring', 'Loading detection models…', 'Initializing');

        try {
            if (!hands) {
                logStartupStage('model loading', 'Creating MediaPipe hands model');
                hands = new Hands({
                    locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469240/${file}`
                });
                hands.setOptions({
                    maxNumHands: 2,
                    modelComplexity: 0,
                    minDetectionConfidence: 0.6,
                    minTrackingConfidence: 0.6
                });
                hands.onResults(onHandResults);
            }

            if (!faceMesh) {
                logStartupStage('face detector initialization', 'Creating MediaPipe face mesh model');
                faceMesh = new FaceMesh({
                    locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh@0.4.1633559619/${file}`
                });
                faceMesh.setOptions({
                    maxNumFaces: 1,
                    // Iris refinement loads a second model and adds per-frame cost.
                    // None of the EAR / MAR / pose / rub metrics use iris points, so keep it off.
                    refineLandmarks: false,
                    minDetectionConfidence: 0.6,
                    minTrackingConfidence: 0.6
                });
                faceMesh.onResults(onFaceResults);
            }

            if (!camera) {
                camera = new Camera(videoElement, {
                    onFrame: async () => {
                        if (!liveFirstFrameReceivedLogged) {
                            liveFirstFrameReceivedLogged = true;
                            startupTiming.firstFrameReceived = performance.now() - startupTiming.pageLoad;
                            logStartupStage('first frame received', 'First live camera frame delivered to onFrame');
                        }
                        await hands.send({ image: videoElement });
                        await faceMesh.send({ image: videoElement });
                        if (!liveFirstInferenceLogged) {
                            liveFirstInferenceLogged = true;
                            startupTiming.firstInference = performance.now() - startupTiming.pageLoad;
                            logStartupStage('first inference', 'First live-frame inference completed (hands + face mesh)');
                        }
                    },
                    width: 640,
                    height: 480
                });
            }

            const warmupCanvas = createWarmupCanvas();
            logStartupStage('model loading', 'Warming MediaPipe models with a preload frame');
            await hands.send({ image: warmupCanvas });
            await faceMesh.send({ image: warmupCanvas });
            startupTiming.firstFrameProcessed = performance.now() - startupTiming.pageLoad;
            logStartupStage('first frame processed', 'Warm-up frame completed');

            monitoringRuntimeReady = true;
            setStartupOverlay(false);
        } catch (err) {
            console.error('[startup] Failed to prepare monitoring runtime', err);
            setStartupOverlay(true, 'Startup issue', 'Could not load monitoring runtime. Please refresh.', 'Failed');
            throw err;
        }
    })();

    return startupPromise;
}

// Audio Context init for audible alarms
function initAudio() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
}

function startAlarm() {
    if (alarmPlaying) return;
    initAudio();
    if (audioContext.state === 'suspended') {
        audioContext.resume();
    }

    oscillator = audioContext.createOscillator();
    gainNode = audioContext.createGain();

    oscillator.type = 'sawtooth';
    oscillator.frequency.setValueAtTime(350, audioContext.currentTime);
    
    // Siren sound (frequency modulation)
    const lfo = audioContext.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.value = 6; // speed of oscillation
    
    const lfoGain = audioContext.createGain();
    lfoGain.gain.value = 180; // depth of pitch change
    
    lfo.connect(lfoGain);
    lfoGain.connect(oscillator.frequency);
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    lfo.start();
    oscillator.start();
    gainNode.gain.setValueAtTime(0.12, audioContext.currentTime);

    alarmPlaying = true;
}

function stopAlarm() {
    if (!alarmPlaying) return;
    if (oscillator) {
        try {
            oscillator.stop();
            oscillator.disconnect();
        } catch(e) {}
        oscillator = null;
    }
    alarmPlaying = false;
}

// Sensitivity control slider listener
sensitivityInput.addEventListener('input', (e) => {
    DROWSINESS_THRESHOLD = parseFloat(e.target.value);
    sensitivityValue.textContent = DROWSINESS_THRESHOLD.toFixed(2);
    localStorage.setItem('drowsinessThreshold', DROWSINESS_THRESHOLD);
});

// Helper math functions
function getDistance(p1, p2) {
    return Math.sqrt(Math.pow(p1.x - p2.x, 2) + Math.pow(p1.y - p2.y, 2));
}

function calculateEAR(landmarks, indices) {
    const p1 = landmarks[indices[0]];
    const p2 = landmarks[indices[1]];
    const p3 = landmarks[indices[2]];
    const p4 = landmarks[indices[3]];
    const p5 = landmarks[indices[4]];
    const p6 = landmarks[indices[5]];

    const d_vert1 = getDistance(p2, p6);
    const d_vert2 = getDistance(p3, p5);
    const d_horiz = getDistance(p1, p4);

    if (d_horiz === 0) return 0;
    return (d_vert1 + d_vert2) / (2.0 * d_horiz);
}

// Calibration mechanism
let isCalibrating = false;
let calibrationFrames = 0;
let calibrationEARSum = 0;
const CALIBRATION_DURATION_FRAMES = 40;

calibrateBtn.addEventListener('click', () => {
    if (!isMonitoring) return;
    isCalibrating = true;
    calibrationFrames = 0;
    calibrationEARSum = 0;
    calibrateBtn.disabled = true;
    calibrateBtn.innerText = "Keep eyes open...";
    statusText.innerText = "Calibrating rest state...";
    statusLight.className = "light yellow";
});

// --- WAKE UP INTERACTIVE CHALLENGES SYSTEM ---
let currentChallengeType = null;
let isChallengeActive = false;
let challengeCooldownUntil = 0; // Timestamp until which challenges are blocked

// Challenge Variables
let mathAnswer = 0;
let memorySeq = [];
let userMemoryInput = [];
let reactionClicksRemaining = 3;
let smileFramesCount = 0;
const SMILE_FRAMES_REQUIRED = 250; // about 10 seconds of steady, moderate smiling

function showChallenge() {
    if (isChallengeActive) return;
    
    // Check cooldown
    const now = Date.now();
    if (now < challengeCooldownUntil) return;
    
    isChallengeActive = true;
    startAlarm();
    
    challengeFeedback.classList.add('hidden');
    challengeFeedback.className = 'challenge-feedback';
    challengeModal.classList.remove('hidden');
    overlayMessage.classList.add('hidden');
    document.getElementById('overlay-title').innerText = 'WAKE UP!';
    document.getElementById('overlay-desc').innerText = 'Stay alert and complete the challenge.';
    
    // Pick random challenge type: math, memory, reaction, smile
    const challenges = ['math', 'memory', 'reaction', 'smile'];
    const chosen = challenges[Math.floor(Math.random() * challenges.length)];
    setupChallenge(chosen);
}

function setupChallenge(type) {
    currentChallengeType = type;
    challengeArea.innerHTML = '';
    
    if (type === 'math') {
        // Generate math challenge
        const num1 = Math.floor(Math.random() * 15) + 10; // 10 to 24
        const num2 = Math.floor(Math.random() * 10) + 5;  // 5 to 14
        const operator = Math.random() > 0.5 ? '+' : '*';
        
        if (operator === '+') {
            mathAnswer = num1 + num2;
        } else {
            mathAnswer = num1 * num2;
        }
        
        challengeArea.innerHTML = `
            <div class="math-expression">${num1} ${operator} ${num2} = ?</div>
            <input type="number" id="math-input-box" class="math-input" autofocus>
            <button id="math-submit" class="btn primary" style="margin-top: 15px;">Verify Answer</button>
        `;
        
        document.getElementById('math-submit').onclick = verifyMathAnswer;
        document.getElementById('math-input-box').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') verifyMathAnswer();
        });
        
    } else if (type === 'memory') {
        // Generate memory sequence
        memorySeq = [];
        userMemoryInput = [];
        for (let i = 0; i < 4; i++) {
            memorySeq.push(Math.floor(Math.random() * 9) + 1); // digits 1-9
        }
        
        challengeArea.innerHTML = `
            <div id="memory-flash" class="memory-sequence-display">${memorySeq.join(' ')}</div>
            <p id="memory-instruction" style="margin-top:10px; font-size:0.9rem; color:#aaa;">Memorize the numbers!</p>
        `;
        
        // Hide numbers after 2 seconds
        setTimeout(() => {
            const memoryFlash = document.getElementById('memory-flash');
            const memoryInstruction = document.getElementById('memory-instruction');
            if (memoryFlash && isChallengeActive && currentChallengeType === 'memory') {
                memoryFlash.innerText = "????";
                memoryFlash.classList.remove('memory-pulse');
                memoryInstruction.innerText = "Type the sequence in order:";
                
                // Show numpad
                challengeArea.innerHTML += `
                    <div class="memory-numpad">
                        <button class="btn-num" onclick="pressMemoryNum(1)">1</button>
                        <button class="btn-num" onclick="pressMemoryNum(2)">2</button>
                        <button class="btn-num" onclick="pressMemoryNum(3)">3</button>
                        <button class="btn-num" onclick="pressMemoryNum(4)">4</button>
                        <button class="btn-num" onclick="pressMemoryNum(5)">5</button>
                        <button class="btn-num" onclick="pressMemoryNum(6)">6</button>
                        <button class="btn-num" onclick="pressMemoryNum(7)">7</button>
                        <button class="btn-num" onclick="pressMemoryNum(8)">8</button>
                        <button class="btn-num" onclick="pressMemoryNum(9)">9</button>
                    </div>
                `;
            }
        }, 2000);
        
    } else if (type === 'reaction') {
        reactionClicksRemaining = 3;
        challengeArea.innerHTML = `
            <div class="reaction-container" id="reaction-box">
                <button id="reaction-btn" class="reaction-target">💥</button>
            </div>
            <p style="margin-top:10px; font-size:0.85rem; color:#aaa;">Click the target 3 times as it jumps!</p>
        `;
        
        const reactionBtn = document.getElementById('reaction-btn');
        reactionBtn.onclick = handleReactionClick;
        relocateTarget();
        
    } else if (type === 'smile') {
        smileFramesCount = 0;
        challengeArea.innerHTML = `
            <div class="pose-challenge-status">
                <span style="font-size:2.5rem;">😊</span>
                <p style="font-weight:600; color:#00f2ea;">Hold a medium smile into the camera!</p>
                <p style="font-size:0.8rem; color:#aaa;">Keep it steady for about 10 seconds</p>
                <div class="pose-progress-track">
                    <div id="pose-progress-fill" class="pose-progress-fill"></div>
                </div>
            </div>
        `;
        const progressFill = document.getElementById('pose-progress-fill');
        if (progressFill) progressFill.style.width = '0%';
    }
}

// Math Challenge logic
function verifyMathAnswer() {
    const input = document.getElementById('math-input-box');
    const val = parseInt(input.value);
    
    if (val === mathAnswer) {
        showChallengeFeedback(true, "Correct! Wake up completed.");
        setTimeout(dismissChallenge, 1000);
    } else {
        showChallengeFeedback(false, "Incorrect! Try again.");
        input.value = '';
        input.focus();
        // Shift to another problem after short delay
        setTimeout(() => setupChallenge('math'), 1000);
    }
}

// Memory Challenge logic
window.pressMemoryNum = function(num) {
    userMemoryInput.push(num);
    
    // Update display showing feedback
    const memoryFlash = document.getElementById('memory-flash');
    memoryFlash.innerText = userMemoryInput.join(' ');
    
    if (userMemoryInput.length === memorySeq.length) {
        const correct = userMemoryInput.every((val, idx) => val === memorySeq[idx]);
        if (correct) {
            showChallengeFeedback(true, "Nice! You're focused.");
            setTimeout(dismissChallenge, 1000);
        } else {
            showChallengeFeedback(false, "Pattern failed! Try another.");
            setTimeout(() => setupChallenge('memory'), 1200);
        }
    }
};

// Reaction Challenge logic
function handleReactionClick() {
    reactionClicksRemaining--;
    if (reactionClicksRemaining <= 0) {
        showChallengeFeedback(true, "Awesome reaction speeds!");
        setTimeout(dismissChallenge, 1000);
    } else {
        relocateTarget();
    }
}

function relocateTarget() {
    const reactionBtn = document.getElementById('reaction-btn');
    const box = document.getElementById('reaction-box');
    if (!reactionBtn || !box) return;
    
    const w = box.clientWidth - 50;
    const h = box.clientHeight - 50;
    
    const randomX = Math.floor(Math.random() * w);
    const randomY = Math.floor(Math.random() * h);
    
    reactionBtn.style.left = `${randomX}px`;
    reactionBtn.style.top = `${randomY}px`;
    reactionBtn.innerText = `${reactionClicksRemaining}`;
}

// Smile verification runs on facial landmarks loop
function checkSmileChallenge(landmarks) {
    const progressFill = document.getElementById('pose-progress-fill');
    if (!progressFill || !landmarks) return;

    const leftEye = landmarks[33] || landmarks[133];
    const rightEye = landmarks[263] || landmarks[362];
    const mouthLeft = landmarks[61] || landmarks[78];
    const mouthRight = landmarks[291] || landmarks[308];
    const upperLip = landmarks[13] || landmarks[0];
    const lowerLip = landmarks[14] || landmarks[17];

    if (!leftEye || !rightEye || !mouthLeft || !mouthRight || !upperLip || !lowerLip) return;

    const eyeWidth = getDistance(leftEye, rightEye);
    const mouthWidth = getDistance(mouthLeft, mouthRight);
    const mouthHeight = getDistance(upperLip, lowerLip);

    if (eyeWidth === 0) return;

    const smileRatio = mouthWidth / eyeWidth;
    const mouthLift = ((leftEye.y + rightEye.y) / 2) - ((mouthLeft.y + mouthRight.y) / 2);
    const smileStrength = Math.max(0, Math.min(1,
        (smileRatio - 0.45) * 1.15 + Math.max(0, mouthLift) * 1.8 + (mouthHeight > 0.003 ? 0.05 : 0)
    ));

    if (smileStrength > 0.22 && mouthHeight > 0.0025) {
        smileFramesCount = Math.min(SMILE_FRAMES_REQUIRED, smileFramesCount + 1);
    } else if (smileFramesCount > 0) {
        smileFramesCount = Math.max(0, smileFramesCount - 0.7);
    }

    const pct = Math.min(100, (smileFramesCount / SMILE_FRAMES_REQUIRED) * 100);
    progressFill.style.width = `${pct}%`;

    if (smileFramesCount >= SMILE_FRAMES_REQUIRED) {
        showChallengeFeedback(true, "Perfect smile detected!");
        setTimeout(() => {
            overlayMessage.classList.remove('hidden');
            document.getElementById('overlay-title').innerText = 'YOU ARE AWAKE!';
            document.getElementById('overlay-desc').innerText = 'Great job — you completed the wake-up challenge.';
            dismissChallenge();
        }, 700);
    }
}

function showChallengeFeedback(isSuccess, text) {
    challengeFeedback.innerText = text;
    challengeFeedback.classList.remove('hidden');
    if (isSuccess) {
        challengeFeedback.className = 'challenge-feedback success';
        // Add points bonus via local JS increment (server side gets updated too)
        focusScore = Math.min(100, focusScore + 10);
    } else {
        challengeFeedback.className = 'challenge-feedback error';
        focusScore = Math.max(0, focusScore - 5);
    }
}

function dismissChallenge() {
    challengeModal.classList.add('hidden');
    isChallengeActive = false;
    currentChallengeType = null;
    consecutiveDrowsyFrames = 0;
    stopAlarm();

    // Set 5 second cooldown to prevent immediate re-triggering
    challengeCooldownUntil = Date.now() + 5000;

    statusText.innerText = "Monitoring";
    statusLight.className = "light green";
    overlayMessage.classList.add('hidden');
}

// Log alarm event in SQLite in real time
async function logAlertEventToServer(severity, reason) {
    if (!activeSessionId) return;
    try {
        await fetch('/api/session/alert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: activeSessionId,
                severity_level: severity,
                trigger_reason: reason
            })
        });
    } catch(err) {
        console.error('Failed to log alert event to database:', err);
    }
}

// --- MEDIAPAPE CALLBACKS ---

// HANDS RESULTS
function onHandResults(results) {
    if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
        latestHandLandmarks = results.multiHandLandmarks;
    } else {
        latestHandLandmarks = null;
    }
}

// FACE MESH (MAIN loop callback)
function onFaceResults(results) {
    if (!isMonitoring) return;
    
    // Draw raw image to canvas
    canvasCtx.save();
    canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
    canvasCtx.drawImage(results.image, 0, 0, canvasElement.width, canvasElement.height);

    if (!liveFirstRenderedFrameLogged) {
        liveFirstRenderedFrameLogged = true;
        startupTiming.firstRenderedFrame = performance.now() - startupTiming.pageLoad;
        logStartupStage('first rendered frame', 'First live frame drawn to output canvas');
    }

    let avgEAR = 0;
    
    // Face details
    if (results.multiFaceLandmarks && results.multiFaceLandmarks.length > 0) {
        latestFaceLandmarks = results.multiFaceLandmarks[0];
        const landmarks = latestFaceLandmarks;
        
        // Draw Face mesh outlines
        // Eye Aspect Ratio indices
        const leftIndices = [33, 160, 158, 133, 153, 144];
        const rightIndices = [362, 385, 387, 263, 373, 380];
        
        const leftEAR = calculateEAR(landmarks, leftIndices);
        const rightEAR = calculateEAR(landmarks, rightIndices);
        avgEAR = (leftEAR + rightEAR) / 2.0;
        
        // Update display numbers
        earLeftDisplay.innerText = leftEAR.toFixed(2);
        earRightDisplay.innerText = rightEAR.toFixed(2);
        earAvgDisplay.innerText = avgEAR.toFixed(2);
        
        // Handle Calibration
        if (isCalibrating) {
            calibrationFrames++;
            calibrationEARSum += avgEAR;
            statusText.innerText = `Calibrating: ${Math.round((calibrationFrames / CALIBRATION_DURATION_FRAMES) * 100)}%`;
            
            if (calibrationFrames >= CALIBRATION_DURATION_FRAMES) {
                isCalibrating = false;
                const baseEAR = calibrationEARSum / calibrationFrames;
                // Set threshold to 75% of resting state
                let calculatedThreshold = baseEAR * 0.75;
                if (calculatedThreshold < 0.15) calculatedThreshold = 0.15;
                if (calculatedThreshold > 0.35) calculatedThreshold = 0.35;
                
                DROWSINESS_THRESHOLD = calculatedThreshold;
                localStorage.setItem('drowsinessThreshold', DROWSINESS_THRESHOLD);
                
                sensitivityInput.value = DROWSINESS_THRESHOLD;
                sensitivityValue.innerText = DROWSINESS_THRESHOLD.toFixed(2);
                
                calibrateBtn.disabled = false;
                calibrateBtn.innerText = "Calibrate Eyes";
                statusText.innerText = "Calibration Done!";
                statusLight.className = "light green";
            }
            canvasCtx.restore();
            return;
        }
        
        // --- PROCESS ACTIVE CHALLENGES CONTROLS ---
        if (isChallengeActive) {
            if (currentChallengeType === 'smile') {
                checkSmileChallenge(landmarks);
            }
            // Draw mesh in red/magenta while challenge is active
            drawFaceMeshMesh(landmarks, "rgba(255, 0, 85, 0.4)");
            canvasCtx.restore();
            return;
        }
        
        // --- NORMAL MONITORING LOGICS ---
        //
        // Trigger model:
        //   * Sustained EYE CLOSURE is the ONLY driver of the critical wake-up
        //     challenge. consecutiveDrowsyFrames counts consecutive closed-eye
        //     frames and nothing else.
        //   * Yawns, head tilt, looking down, and eye-rubbing are WARNING-only
        //     indicators. They surface a Level-1 warning but never accumulate
        //     toward, or fire, the challenge on their own.
        //   * A genuine drowsy NOD (a fast downward pitch drop = loss of muscle
        //     control) does not fire anything by itself either; it only lowers
        //     the closure frame count needed when the eyes are also closed.

        // 1. Eye closure (the core microsleep signal)
        const eyesClosed = avgEAR < DROWSINESS_THRESHOLD;

        // BLINK COUNTING
        if (eyesClosed) {
            if (!isBlinking) isBlinking = true;
        } else if (isBlinking) {
            blinksCount++;
            isBlinking = false;
        }

        // 2. Yawn logic: Mouth Opening Ratio (warning indicator)
        const pUpper = landmarks[13];
        const pLower = landmarks[14];
        const pLeft = landmarks[78];
        const pRight = landmarks[308];
        const distVert = getDistance(pUpper, pLower);
        const distHoriz = getDistance(pLeft, pRight);

        let mar = 0;
        if (distHoriz > 0) mar = distVert / distHoriz;

        const isYawning = mar > YAWN_THRESHOLD;
        if (isYawning && frameCounter - lastYawnFrame > 60) {
            yawnsCount++;
            logYawnsDisplay.innerText = yawnsCount;
            lastYawnFrame = frameCounter;
        }

        // 3. Head pose (roll = tilt, pitch = up/down)
        const eyeDx = landmarks[263].x - landmarks[33].x;
        const eyeDy = landmarks[263].y - landmarks[33].y;
        const headRollAngle = Math.abs(Math.atan2(eyeDy, eyeDx));

        const nosePoint = landmarks[1];
        const chinPoint = landmarks[152];
        const midEyesPoint = landmarks[168];
        const noseToChin = getDistance(nosePoint, chinPoint);
        const midEyesToNose = getDistance(midEyesPoint, nosePoint);
        const headPitchRatio = midEyesToNose > 0 ? noseToChin / midEyesToNose : 1.0;

        const isTilted = headRollAngle > TILT_THRESHOLD;
        const isLookingDown = headPitchRatio < PITCH_THRESHOLD_DOWN;

        // Genuine drowsy nod = the head DROPS quickly (loss of muscle control),
        // not merely holding a looking-down pose. Measured as per-frame fall in
        // the pitch ratio. A slow, deliberate look-down has near-zero velocity
        // and is intentionally ignored here.
        let drowsyNodThisFrame = false;
        if (lastPitchRatio !== null) {
            const pitchDrop = lastPitchRatio - headPitchRatio;
            if (pitchDrop > NOD_PITCH_DROP_VELOCITY && isLookingDown) {
                drowsyNodThisFrame = true;
                lastDrowsyNodFrame = frameCounter;
                if (frameCounter - lastNodFrame > 60) {
                    nodsCount++;
                    lastNodFrame = frameCounter;
                }
            }
        }
        lastPitchRatio = headPitchRatio;

        // 4. Hand touching eyes/rubbing (warning indicator)
        let isRubbing = false;
        if (latestHandLandmarks) {
            const eyeCoordinates = [landmarks[33], landmarks[133], landmarks[362], landmarks[263]];
            const fingertips = [4, 8, 12, 16, 20];

            for (const hand of latestHandLandmarks) {
                for (const tipIdx of fingertips) {
                    const fingerTip = hand[tipIdx];
                    for (const eyePoint of eyeCoordinates) {
                        if (getDistance(fingerTip, eyePoint) < 0.08) {
                            isRubbing = true;
                            canvasCtx.strokeStyle = "#ff0055";
                            canvasCtx.lineWidth = 3;
                            canvasCtx.beginPath();
                            canvasCtx.moveTo(fingerTip.x * canvasElement.width, fingerTip.y * canvasElement.height);
                            canvasCtx.lineTo(eyePoint.x * canvasElement.width, eyePoint.y * canvasElement.height);
                            canvasCtx.stroke();
                            break;
                        }
                    }
                    if (isRubbing) break;
                }
                if (isRubbing) break;
            }
        }

        // A recent drowsy nod stays "fresh" for a short window so it can
        // corroborate eye closure even if the two peak a few frames apart.
        const nodFresh = (frameCounter - lastDrowsyNodFrame) < NOD_CORROBORATION_WINDOW;

        // --- ALERT OR MONITOR DECISIONS ---
        // Only sustained eye closure advances the critical counter.
        if (eyesClosed) {
            consecutiveDrowsyFrames++;

            // With a corroborating drowsy nod, a shorter closure fires the challenge.
            const triggerFrames = nodFresh ? EAR_CLOSED_FRAMES_WITH_NOD : EAR_CLOSED_FRAMES_TO_TRIGGER;

            // Level 1: gentle warning after brief sustained closure
            if (consecutiveDrowsyFrames === WARNING_CLOSED_FRAMES) {
                statusText.innerText = "Warning: Eyes Closing";
                statusLight.className = "light yellow";
                speakVoiceWarning("Eyes Closed");
                logAlertEventToServer("Warning", "Eyes Closing");
            }

            // Level 2: critical challenge on sustained closure (optionally + nod)
            if (consecutiveDrowsyFrames === triggerFrames) {
                const reason = nodFresh ? "Eyes Closed + Head Nod" : "Prolonged Eye Closure";
                alertsCount++;
                logAlertsDisplay.innerText = alertsCount;

                focusScore = Math.max(10, focusScore - 8);
                logFocusDisplay.innerText = `${Math.round(focusScore)}%`;

                statusText.innerText = "CRITICAL ALERT!";
                statusLight.className = "light red";
                overlayMessage.classList.remove('hidden');
                document.getElementById('overlay-title').innerText = "WAKE UP!";
                document.getElementById('overlay-desc').innerText = `${reason} detected`;

                logAlertEventToServer("Critical", reason);
                showChallenge();
            }

            drawFaceMeshMesh(landmarks, "rgba(255, 0, 85, 0.35)");
        } else {
            // Eyes are open: reset the microsleep counter. Non-closure signals
            // (yawn / tilt / looking down / rubbing) surface only as warnings.
            consecutiveDrowsyFrames = 0;

            let warnReason = "";
            if (isYawning) warnReason = "Yawning";
            else if (isTilted) warnReason = "Head Tilted";
            else if (isRubbing) warnReason = "Eye Rubbing";
            else if (isLookingDown) warnReason = "Looking Down";

            if (warnReason) {
                statusText.innerText = `Warning: ${warnReason}`;
                statusLight.className = "light yellow";
                speakVoiceWarning(warnReason);
                drawFaceMeshMesh(landmarks, "rgba(255, 193, 7, 0.30)");
            } else {
                statusText.innerText = "Monitoring";
                statusLight.className = "light green";
                overlayMessage.classList.add('hidden');
                drawFaceMeshMesh(landmarks, "rgba(0, 242, 234, 0.3)");
            }
        }

        // Whether any drowsiness indicator is present (for alertness scoring only)
        const anyIndicator = eyesClosed || isYawning || isTilted || isRubbing || drowsyNodThisFrame;
        
        // --- CALCULATE LIVE ALERTNESS PERCENT ---
        let liveScore = 100;
        const maxHealthyEAR = DROWSINESS_THRESHOLD * 1.5;
        
        if (avgEAR <= DROWSINESS_THRESHOLD) {
            liveScore = 0;
        } else if (avgEAR >= maxHealthyEAR) {
            liveScore = 100;
        } else {
            liveScore = ((avgEAR - DROWSINESS_THRESHOLD) / (maxHealthyEAR - DROWSINESS_THRESHOLD)) * 100;
        }
        
        // Penalties on alertness score for warning-level indicators
        if (anyIndicator) {
            if (isYawning) liveScore = Math.min(25, liveScore);
            if (isTilted || drowsyNodThisFrame) liveScore = Math.min(20, liveScore);
        }
        
        // Add current reading to history for end statistics average
        alertnessHistory.push(liveScore);
        
        // Update alertness bar in HUD
        alertnessPercent.innerText = `${Math.round(liveScore)}%`;
        alertnessBar.style.width = `${liveScore}%`;
        
        if (liveScore > 65) {
            alertnessBar.style.background = 'linear-gradient(90deg, #00f2ea, #00b4d8)';
        } else if (liveScore > 30) {
            alertnessBar.style.background = 'linear-gradient(90deg, #ffd700, #ff9100)';
        } else {
            alertnessBar.style.background = 'linear-gradient(90deg, #ff0055, #d50000)';
        }
        
    } else {
        // No face landmarks detected
        statusText.innerText = "No Face Detected";
        statusLight.className = "light";
        if (alarmPlaying && !isChallengeActive) {
            stopAlarm();
        }
        latestFaceLandmarks = null;
    }
    
    frameCounter++;
    canvasCtx.restore();
}

// Speak warnings using client web voice synthesizer
let lastSpokenTime = 0;
function speakVoiceWarning(reason) {
    const now = Date.now();
    if (now - lastSpokenTime < 5000) return; // limit rate
    lastSpokenTime = now;
    
    let speechText = "Warning. Drowsiness detected.";
    if (reason === "Eyes Closed" || reason === "Eyes Closing") speechText = "Attention. Please keep your eyes open.";
    if (reason === "Yawning") speechText = "Alert. Take a deep breath or stretch.";
    if (reason === "Head Tilted" || reason === "Looking Down") speechText = "Warning. Raise your head.";
    if (reason === "Eye Rubbing") speechText = "Avoid rubbing your eyes. You are fatigued.";
    
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(speechText);
        utterance.rate = 1.1;
        window.speechSynthesis.speak(utterance);
    }
}

// Draw Face Mesh lines to Canvas
function drawFaceMeshMesh(landmarks, strokeColor) {
    canvasCtx.strokeStyle = strokeColor;
    canvasCtx.lineWidth = 1.0;
    
    try {
        const oval = window.FACEMESH_FACE_OVAL || (typeof FACEMESH_FACE_OVAL !== 'undefined' ? FACEMESH_FACE_OVAL : null);
        const lips = window.FACEMESH_LIPS || (typeof FACEMESH_LIPS !== 'undefined' ? FACEMESH_LIPS : null);
        const leftEye = window.FACEMESH_LEFT_EYE || (typeof FACEMESH_LEFT_EYE !== 'undefined' ? FACEMESH_LEFT_EYE : null);
        const rightEye = window.FACEMESH_RIGHT_EYE || (typeof FACEMESH_RIGHT_EYE !== 'undefined' ? FACEMESH_RIGHT_EYE : null);
        
        if (oval) drawLines(landmarks, oval);
        if (lips) drawLines(landmarks, lips);
        if (leftEye) drawLines(landmarks, leftEye);
        if (rightEye) drawLines(landmarks, rightEye);
    } catch(e) {
        console.warn("Failed to draw face mesh connections:", e);
    }
}

function drawLines(landmarks, connections) {
    if (!connections || !landmarks) return;
    try {
        for (const connection of connections) {
            const p1 = landmarks[connection[0]];
            const p2 = landmarks[connection[1]];
            if (!p1 || !p2) continue;
            canvasCtx.beginPath();
            canvasCtx.moveTo(p1.x * canvasElement.width, p1.y * canvasElement.height);
            canvasCtx.lineTo(p2.x * canvasElement.width, p2.y * canvasElement.height);
            canvasCtx.stroke();
        }
    } catch(e) {
        console.warn("Error inside drawLines:", e);
    }
}

// Timer clock display
function startTimer() {
    elapsedSeconds = 0;
    logTimeDisplay.innerText = "00:00:00";
    
    elapsedTimerInterval = setInterval(() => {
        elapsedSeconds++;
        const hrs = Math.floor(elapsedSeconds / 3600);
        const mins = Math.floor((elapsedSeconds % 3600) / 60);
        const secs = elapsedSeconds % 60;
        
        logTimeDisplay.innerText = 
            `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
            
        // Slow positive decay for focus score if they go alerts-free
        if (elapsedSeconds % 30 === 0) {
            if (consecutiveDrowsyFrames === 0 && !isChallengeActive) {
                focusScore = Math.min(100, focusScore + 1);
                logFocusDisplay.innerText = `${Math.round(focusScore)}%`;
            }
        }
    }, 1000);
}

function stopTimer() {
    if (elapsedTimerInterval) {
        clearInterval(elapsedTimerInterval);
        elapsedTimerInterval = null;
    }
}

// Control triggers

// Start session
startBtn.addEventListener('click', async () => {
    try {
        setStartupOverlay(true, 'Starting monitoring', 'Requesting camera access…', 'Camera permission');
        logStartupStage('camera permission', 'Waiting for camera access');

        // Request backend starts logging active session
        const resp = await fetch('/api/session/start', { method: 'POST' });
        const data = await resp.json();
        if (data.session_id) {
            activeSessionId = data.session_id;
        }
        
        isMonitoring = true;
        startBtn.disabled = true;
        stopBtn.disabled = false;
        calibrateBtn.disabled = false;
        
        statusText.innerText = "Camera waking...";
        statusLight.className = "light yellow";
        
        // Reset local statistics
        yawnsCount = 0;
        blinksCount = 0;
        nodsCount = 0;
        alertsCount = 0;
        focusScore = 100;
        alertnessHistory = [];
        consecutiveDrowsyFrames = 0;

        // Reset per-session startup markers so timing reflects this Start click
        liveFirstFrameReceivedLogged = false;
        liveFirstInferenceLogged = false;
        liveFirstRenderedFrameLogged = false;

        // Reset nod-velocity tracking state
        lastPitchRatio = null;
        lastDrowsyNodFrame = -1000;
        
        logYawnsDisplay.innerText = 0;
        logAlertsDisplay.innerText = 0;
        logFocusDisplay.innerText = "100%";
        
        initAudio();

        await initializeMonitoringRuntime();
        startupTiming.cameraPermission = performance.now() - startupTiming.pageLoad;
        logStartupStage('camera initialization', 'Starting camera stream');
        setStartupOverlay(true, 'Starting monitoring', 'Opening camera feed…', 'Camera initialization');
        await camera.start();
        startupTiming.cameraInitialization = performance.now() - startupTiming.pageLoad;
        logStartupStage('camera initialization', 'Camera stream started');
        setStartupOverlay(false);
        
        statusText.innerText = "Monitoring";
        statusLight.className = "light green";
        document.getElementById('rec-dot').classList.add('pulse-dot');
        
        startTimer();
        
    } catch(err) {
        console.error('Failed to boot monitoring session:', err);
        statusText.innerText = "Access Failed";
        statusLight.className = "light red";
        startBtn.disabled = false;
        stopBtn.disabled = true;
        setStartupOverlay(true, 'Startup issue', 'Could not start monitoring. Please allow camera access and refresh.', 'Failed');
    }
});

initializeMonitoringRuntime().catch(() => {});

// Stop session
stopBtn.addEventListener('click', async () => {
    isMonitoring = false;
    startBtn.disabled = false;
    stopBtn.disabled = true;
    calibrateBtn.disabled = true;
    
    stopTimer();
    stopAlarm();
    
    statusText.innerText = "Stopped";
    statusLight.className = "light";
    document.getElementById('rec-dot').className = '';
    overlayMessage.classList.add('hidden');
    challengeModal.classList.add('hidden');
    isChallengeActive = false;
    
    await camera.stop();
    
    // Average Alertness
    let sum = 0;
    alertnessHistory.forEach(v => sum += v);
    let avgAlertnessVal = alertnessHistory.length > 0 ? (sum / alertnessHistory.length) : 100.0;
    
    // Post session stats to server
    if (activeSessionId) {
        try {
            statusText.innerText = "Logging session...";
            const resp = await fetch('/api/session/end', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: activeSessionId,
                    duration_seconds: elapsedSeconds,
                    avg_alertness: avgAlertnessVal,
                    yawns_count: yawnsCount,
                    blinks_count: blinksCount,
                    nods_count: nodsCount,
                    alerts_count: alertsCount,
                    focus_score: focusScore
                })
            });
            const result = await resp.json();
            
            // If achievements unlocked, alert user
            if (result.new_achievements && result.new_achievements.length > 0) {
                let unlockedTitles = result.new_achievements.map(a => `🏆 ${a.title}: ${a.description}`).join('\n');
                alert(`🎉 Achievements Unlocked! 🎉\n\n${unlockedTitles}\n\nAdded +${result.points_earned} XP!`);
            }
            
            // Redirect back to dashboard
            window.location.href = '/dashboard';
        } catch(err) {
            console.error('Error stopping monitoring:', err);
            window.location.href = '/dashboard';
        }
    }
});

// Snapshot generator
if (photoBtn) {
    photoBtn.addEventListener('click', () => {
        const w = canvasElement.width || videoElement.videoWidth || 640;
        const h = canvasElement.height || videoElement.videoHeight || 480;
        const temp = document.createElement('canvas');
        temp.width = w;
        temp.height = h;
        const tctx = temp.getContext('2d');
        // Mirror snapshot naturally
        tctx.translate(w, 0);
        tctx.scale(-1, 1);
        
        if (canvasElement && canvasElement.width > 0) {
            tctx.drawImage(canvasElement, 0, 0, w, h);
        } else {
            tctx.drawImage(videoElement, 0, 0, w, h);
        }
        
        const link = document.createElement('a');
        link.href = temp.toDataURL('image/png');
        link.download = `session_snapshot_${Date.now()}.png`;
        document.body.appendChild(link);
        link.click();
        link.remove();
    });
}

function resizeCanvas() {
    canvasElement.width = videoElement.videoWidth || 640;
    canvasElement.height = videoElement.videoHeight || 480;
}
videoElement.addEventListener('loadedmetadata', resizeCanvas);
window.addEventListener('resize', resizeCanvas);
