// Initialize canvas and context
const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

// Slider UI
const radiusSlider = document.getElementById("radiusSlider");
const radiusValue = document.getElementById("radiusValue");

// Game dimensions
const width = 750;
const height = 750;
const centerX = width / 2;
const centerY = height / 2;

// Constants
const G = 6.67430e-11;
const c = 299792458;

// Orbit parameters
let BH_mass = 1e36;
let display_scale = 0.00000005;
let orbit_radius = 1;
let display_orbital_radius = orbit_radius * display_scale;
let angle = 0;
let angular_velocity = calculateAngularOrbitalVelocity(orbit_radius, BH_mass);
let BH_radius_px = calculateBHRadius(BH_mass) * display_scale;
let time_dilation_factor = 1;
let spiral_mode = false;
let fell_in = false;

// Input variables
let waiting_for_radius = true;

// Time tracking
let orbit_start_time = null;
let elapsed_orbit_time = 0;
let final_player_time = 0;
let final_outside_time = 0;

// Game state
let running = true;
let orbit_ended = false;

// UI elements
const leave_button_rect = { x: 550, y: 20, width: 165, height: 40 };
const try_leave_button_rect = { x: 480, y: 20, width: 260, height: 40 };
const try_again_button_rect = { x: width / 2 - 60, y: height / 2 + 120, width: 140, height: 40 };

// Images
const background = new Image();
background.src = "coding_blackhole_backround.png";

const spaceship = new Image();
spaceship.src = "coding_blackhole_spaceship.png";

// Functions
function calculateAngularOrbitalVelocity(radius, BH_mass) {
  return Math.sqrt(G * BH_mass / Math.pow(radius, 3));
}

function calculateBHRadius(BH_mass) {
  return 2 * G * BH_mass / (c * c);
}

function calculateTimeElapseOutside(local_time, radius, BH_mass) {
  const factor = 1 / Math.sqrt(1 - (3 * G * BH_mass) / (radius * c * c));
  return local_time * factor;
}

function calculateISCO(BH_mass) {
  return 3 * calculateBHRadius(BH_mass);
}

function formatTime(seconds) {
  const time_units = [
    { name: "year", seconds: 365 * 24 * 3600 },
    { name: "day", seconds: 24 * 3600 },
    { name: "hour", seconds: 3600 },
    { name: "minute", seconds: 60 },
    { name: "second", seconds: 1 }
  ];

  for (const unit of time_units) {
    if (seconds >= unit.seconds) {
      const value = seconds / unit.seconds;
      const rounded = Math.round(value * 10) / 10;
      const plural = rounded !== 1 ? 's' : '';
      return `${rounded} ${unit.name}${plural}`;
    }
  }

  return `${seconds} seconds`;
}

function titleScreen() {
  ctx.fillStyle = "black";
  ctx.fillRect(0, 0, width, height);

  ctx.font = "24px Arial";
  ctx.fillStyle = "white";
  ctx.textAlign = "center";

  ctx.fillText("Black Hole Orbit Simulator", width / 2, 180);
  ctx.fillText("Press any key to start", width / 2, 370);

  return new Promise(resolve => {
    function handleKeyDown() {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleMouseDown);
      resolve();
    }

    function handleMouseDown() {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleMouseDown);
      resolve();
    }

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleMouseDown);
  });
}

function drawRect(rect, color) {
  ctx.fillStyle = color;
  ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
}

function isPointInRect(x, y, rect) {
  return x >= rect.x && x <= rect.x + rect.width &&
         y >= rect.y && y <= rect.y + rect.height;
}

function drawTextCentered(text, x, y, color = "white") {
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

function drawButton(rect, text, color) {
  drawRect(rect, color);

  ctx.fillStyle = "white";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  drawTextCentered(text, rect.x + rect.width / 2, rect.y + rect.height / 2);

  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
}

function showEndScreen() {
  ctx.fillStyle = "black";
  ctx.fillRect(0, 0, width, height);

  ctx.font = "24px Arial";
  ctx.fillStyle = "white";
  ctx.textAlign = "center";

  if (fell_in) {
    drawTextCentered("You fell into the black hole,", width / 2, height / 2 - 60);
    drawTextCentered("with no hopes of leaving.", width / 2, height / 2 - 30);
    drawTextCentered("Try an orbit outside the innermost stable orbit.", width / 2, height / 2);

    drawButton(try_again_button_rect, "TRY AGAIN", "rgb(0, 100, 200)");
  } else {
    drawTextCentered("You left orbit.", width / 2, height / 2 - 40);

    const final_player_timeformatted = formatTime(final_player_time);
    drawTextCentered(`Time in orbit: ${final_player_timeformatted}`, width / 2, height / 2);

    const final_outside_timeformatted = formatTime(final_outside_time);
    drawTextCentered(`${final_outside_timeformatted} have passed.`, width / 2, height / 2 + 40);

    drawTextCentered(`Time dilation factor: ${time_dilation_factor.toFixed(2)}`, width / 2, height / 2 + 80);

    drawButton(try_again_button_rect, "TRY AGAIN", "rgb(0, 100, 200)");
  }
}

function showOrbit() {
  // Draw background
  ctx.drawImage(background, 0, 0, width, height);

  // Calculate orbital positions
  const s_x = centerX + display_orbital_radius * Math.cos(angle) - 25;
  const s_y = centerY + display_orbital_radius * Math.sin(angle) - 25;

  if (!waiting_for_radius && !orbit_ended) {
    if (orbit_radius > calculateBHRadius(BH_mass)) {
      angle += angular_velocity / frameRate;
    }
  }

  if (!waiting_for_radius) {
    if (spiral_mode && orbit_radius > calculateBHRadius(BH_mass)) {
      orbit_radius *= 0.99; // spiral in gradually
      display_orbital_radius = orbit_radius * display_scale;
      angular_velocity = calculateAngularOrbitalVelocity(orbit_radius, BH_mass);
    }
  }

  // Draw black hole
  ctx.beginPath();
  ctx.arc(centerX, centerY, BH_radius_px, 0, Math.PI * 2);
  ctx.fillStyle = "black";
  ctx.fill();

  // Draw ISCO
  const ISCO_radius = calculateISCO(BH_mass);
  const ISCO_radius_pixels = ISCO_radius * display_scale;
  const number_dashes = 100;

  ctx.strokeStyle = "yellow";
  ctx.beginPath();

  for (let i = 0; i < number_dashes; i++) {
    const theta1 = (2 * Math.PI / number_dashes) * i;
    const theta2 = (2 * Math.PI / number_dashes) * (i + 0.5);

    const x1 = centerX + ISCO_radius_pixels * Math.cos(theta1);
    const y1 = centerY + ISCO_radius_pixels * Math.sin(theta1);
    const x2 = centerX + ISCO_radius_pixels * Math.cos(theta2);
    const y2 = centerY + ISCO_radius_pixels * Math.sin(theta2);

    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
  }

  ctx.stroke();

  // Draw spaceship
  ctx.drawImage(spaceship, s_x, s_y, 50, 50);

  if (!spiral_mode) {
    // Display orbital speed
    const orbital_speed = angular_velocity * orbit_radius;
    const fraction_of_c = orbital_speed / c * 100;

    ctx.font = "24px Arial";
    ctx.fillStyle = "white";
    ctx.textAlign = "left";
    ctx.fillText(`Orbital Speed: ${fraction_of_c.toFixed(2)}% the speed of light`, 10, 30);

    // Display timer
    if (orbit_start_time !== null) {
      const formatted_orbit_time = formatTime(Math.round(elapsed_orbit_time));
      ctx.fillText(`Time in orbit: ${formatted_orbit_time}`, 10, 60);
    }
  }

  if (spiral_mode) {
    drawButton(try_leave_button_rect, "TRY TO LEAVE ORBIT", "rgb(200, 0, 0)");
  } else {
    drawButton(leave_button_rect, "LEAVE ORBIT", "rgb(200, 0, 0)");
  }
}

function showRadiusInput() {
  ctx.drawImage(background, 0, 0, width, height);

  // Draw background box
  const box_width = 600;
  const box_height = 300;
  const box_x = width / 2 - box_width / 2;
  const box_y = 120;

  ctx.fillStyle = "black";
  ctx.fillRect(box_x, box_y, box_width, box_height);

  // Black hole stats
  ctx.font = "24px Arial";
  ctx.fillStyle = "white";
  ctx.textAlign = "center";

  ctx.fillText(`Black Hole Mass: ${BH_mass.toExponential(1)} kg`, width / 2, 170);
  ctx.fillText(`Schwarzschild Radius: ${calculateBHRadius(BH_mass).toExponential(2)} m`, width / 2, 200);

  // Prompt text
  ctx.fillText("Choose your orbit radius with the slider, then press Enter:", width / 2, 260);

  // Selected value display (comes from slider)
  ctx.fillText(`Selected: ${orbit_radius === 0 ? "0" : orbit_radius.toExponential(2)} m`, width / 2, 310);
}

function resetGame() {
  orbit_ended = false;
  waiting_for_radius = true;
  orbit_radius = parseFloat(radiusSlider.value);
  display_orbital_radius = orbit_radius * display_scale;
  angular_velocity = calculateAngularOrbitalVelocity(Math.max(orbit_radius, 1), BH_mass);
  angle = 0;
  elapsed_orbit_time = 0;
  final_player_time = 0;
  final_outside_time = 0;
  spiral_mode = false;
  fell_in = false;
}

// Slider setup (0 on left, max orbit that still stays on screen on right)
function setupSliderRange() {
  const ship_half = 25;     // because you draw 50x50 and offset by -25
  const padding = 10;
  const max_display_radius_px = Math.min(centerX, centerY) - ship_half - padding;

  const orbit_radius_max = max_display_radius_px / display_scale;

  radiusSlider.min = "0";
  radiusSlider.max = String(orbit_radius_max);
  radiusSlider.step = String(orbit_radius_max / 1000);
  radiusSlider.value = String(calculateBHRadius(BH_mass)); // start near horizon

  orbit_radius = parseFloat(radiusSlider.value);
  display_orbital_radius = orbit_radius * display_scale;
  angular_velocity = calculateAngularOrbitalVelocity(Math.max(orbit_radius, 1), BH_mass);

  radiusValue.textContent = `Selected: ${orbit_radius.toExponential(2)} m`;
}

radiusSlider.addEventListener("input", () => {
  orbit_radius = parseFloat(radiusSlider.value);
  display_orbital_radius = orbit_radius * display_scale;
  angular_velocity = calculateAngularOrbitalVelocity(Math.max(orbit_radius, 1), BH_mass);
  radiusValue.textContent = `Selected: ${orbit_radius === 0 ? "0" : orbit_radius.toExponential(2)} m`;
});

// Event listeners
canvas.addEventListener('click', (event) => {
  const rect = canvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;

  if (orbit_ended) {
    if (isPointInRect(mouseX, mouseY, try_again_button_rect)) {
      resetGame();
    }
  } else if (!waiting_for_radius) {
    if (spiral_mode && isPointInRect(mouseX, mouseY, try_leave_button_rect)) {
      orbit_ended = true;
      fell_in = true;
    } else if (isPointInRect(mouseX, mouseY, leave_button_rect)) {
      final_player_time = elapsed_orbit_time;
      final_outside_time = calculateTimeElapseOutside(final_player_time, orbit_radius, BH_mass);
      time_dilation_factor = final_outside_time / final_player_time;
      orbit_ended = true;
    }
  }
});

document.addEventListener('keydown', (event) => {
  if (waiting_for_radius) {
    if (event.key === 'Enter') {
      orbit_radius = parseFloat(radiusSlider.value);
      display_orbital_radius = orbit_radius * display_scale;
      angular_velocity = calculateAngularOrbitalVelocity(Math.max(orbit_radius, 1), BH_mass);

      // If they pick 0 or anything inside the horizon, they’re done instantly
      if (orbit_radius <= calculateBHRadius(BH_mass)) {
        fell_in = true;
        orbit_ended = true;
        waiting_for_radius = false;
        return;
      }

      // Check if within ISCO
      const ISCO_radius = calculateISCO(BH_mass);
      spiral_mode = orbit_radius < ISCO_radius;

      // Start game
      waiting_for_radius = false;

      // Start timer
      orbit_start_time = Date.now();
    }
  }
});

// Game loop
const frameRate = 60;
let lastTime = 0;

function gameLoop(timestamp) {
  if (!lastTime) lastTime = timestamp;
  const deltaTime = timestamp - lastTime;

  if (deltaTime >= 1000 / frameRate) {
    // Update elapsed time
    if (!waiting_for_radius && !orbit_ended && orbit_start_time !== null) {
      elapsed_orbit_time += 1 / frameRate;
    }

    // Render based on game state
    if (orbit_ended) {
      showEndScreen();
    } else if (waiting_for_radius) {
      showRadiusInput();
    } else {
      showOrbit();
    }

    lastTime = timestamp;
  }

  if (running) {
    requestAnimationFrame(gameLoop);
  }
}

// Start the game
async function startGame() {
  setupSliderRange();
  await titleScreen();
  requestAnimationFrame(gameLoop);
}

startGame();