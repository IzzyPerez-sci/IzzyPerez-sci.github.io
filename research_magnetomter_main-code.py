from machine import SPI, I2C, Pin, ADC
import network, socket, time, json
import sdcard, uos


#SPI setup for SD card
spi = SPI(0, sck=Pin(18), mosi=Pin(19), miso=Pin(16))  #initate with the pins im using
cs = Pin(17)
sd = sdcard.SDCard(spi, cs) 
uos.mount(sd, '/sd') #mounts  SD card to the directory /sd
#print(uos.listdir('/sd')) 

#f = open("/sd/field_data.txt", "a")

#SETUP VARIABLES
#magnetometer setup
M_ADDRESS = 0x30 #sensors I2C adress '0110000' (binary) (this is whats in documenttation)
M_STATUS = 0x08 #read this to know when measurement is finished #'Status 08H Device status'
M_CTRL0  = 0x09 #start measurement
M_XOUT0  = 0x00 #starting address for XYZ data

#REGISTER MAP data sheet uses NNH while code uses 0xNN
#00H 0x00 → Xout0 (Xout [17:10])
#01H 0x01 → Xout1 (Xout [9:2])
#02H 0x02 → Yout0 (Yout [17:10])
#03H 0x03 → Yout1 (Yout [9:2])
#04H 0x04 → Zout0 (Zout [17:10])
#05H 0x05 → Zout1 (Zout [9:2])
#06H 0x06 → XYZout2 (Xout[1:0], Yout[1:0], Zout[1:0])
#07H 0x07 → Tout (Temperature output)
#08H 0x08 → Status (Device Status)
#09H 0x09 → Internal control 0 (Control register 0)
#0AH 0x0A→ Internal control 1 (Control register 1)
#0BH 0x0B→ Internal control 2 (Control register 2)
#0CH 0x0C→ Internal control 3 (Control register 3)
#2FH 0x2F→ Product ID 1 (Product ID)

M_SCALE = .0625 * .1 #we are in 18-bit resolution! e-7 #what should the scale be
#Test me and derric did
#M_OFFSETX = 132000.0
#M_OFFSETY = 131493.0
#M_OFFSETZ = 131493.0

#Assuming offset is (2^18)/2 = 131072
M_OFFSETX = 131072
M_OFFSETY = 131072
M_OFFSETZ = 131072

i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100_000) #setting up which wires go where,
#"I2C Slave, FAST(≤400KHz) mode"

i2c.writeto_mem(M_ADDRESS, 0x0A, b'\x00') #puts in bandwidth 00 mode!
#M_ADDR is the address defined above
#0x0A is internal controll 1
#b'\x00' sets all the bits to 0 in internal control 1

#store session data
session_data = []
samples = []

#wifi set up
ssid = "my-wifi"
password = "Password1"

led = Pin("LED", Pin.OUT)
state = "OFF"

# time sync info from browser (in ms)
sync_time_ms = None    # time from the user device (ms since 1970)
sync_tick = None       # ticks_ms() when we got that time

# averaging over multiple raw samples before logging to SD
AVG_N = 50             # number of raw samples to average
avg_count = 0
sum_x = 0.0
sum_y = 0.0
sum_z = 0.0
sum_temp = 0.0
window_start_tick = None
window_end_tick = None


#FUNCTIONS

def read_xyz():
    '''
This function triggers one xyz measuremnt from the MMC5983MA sensor
    '''
    #trigger one magnetic measurement
    i2c.writeto_mem(M_ADDRESS, M_CTRL0, b'\x01')
    #this talkes to sensor, goes to internal control 0 and writes 00000001
    #this triggers bit 0 TM_M (Take magnetic field measurement) which resets to 0 when done automatically

    # wait for magnetic data ready (status bit 0)
    while not (i2c.readfrom_mem(M_ADDRESS, M_STATUS, 1)[0] & 0x01):
        pass
    
    # read 7 bytes: X0,X1,Y0,Y1,Z0,Z1,XYZout2
    data = i2c.readfrom_mem(M_ADDRESS, M_XOUT0, 7) #start at X address read 7 adresses
    x = (((data[0] << 10) | (data[1] << 2) | ((data[6] >> 6) & 0x03)) - M_OFFSETX) * M_SCALE
    y = (((data[2] << 10) | (data[3] << 2) | ((data[6] >> 4) & 0x03)) - M_OFFSETY) * M_SCALE
    z = (((data[4] << 10) | (data[5] << 2) | ((data[6] >> 2) & 0x03)) - M_OFFSETZ) * M_SCALE

    # ----- temperature measurement -----
    # bit 1 in CTRL0 is TM_T (take temperature measurement)
    i2c.writeto_mem(M_ADDRESS, M_CTRL0, b'\x02')

    # wait for temperature ready (status bit 1)
    while not (i2c.readfrom_mem(M_ADDRESS, M_STATUS, 1)[0] & 0x02):
        pass

    # read raw temperature from register 0x07 (Tout)
    temp = i2c.readfrom_mem(M_ADDRESS, 0x07, 1)[0]

    #
    return x, y, z, temp

def sample_100hz(f, flush_every=30, next_tick=None):
    '''
    Sample magnetometer at approximatly 100Hz,
    but log only an average of AVG_N samples to the SD card.
    '''
    global sync_time_ms, sync_tick
    global avg_count, sum_x, sum_y, sum_z, sum_temp
    global window_start_tick, window_end_tick

    period = 10  # 10ms = 100Hz (actual rate limited by sensor timing)
    
    #initialize timing on 
    if next_tick is None:
        next_tick = time.ticks_ms()
    
    #next measurement time based on previous tick
    next_tick = time.ticks_add(next_tick, period)
    
    #take one raw measurement
    t = time.ticks_ms()
    x, y, z, temp = read_xyz()

    # accumulate for averaging
    if avg_count == 0:
        window_start_tick = t
    window_end_tick = t

    avg_count += 1
    sum_x += x
    sum_y += y
    sum_z += z
    sum_temp += temp

    # when we have AVG_N samples, compute average and log ONE line
    if avg_count >= AVG_N and window_start_tick is not None and window_end_tick is not None:
        center_tick = (window_start_tick + window_end_tick) // 2
        avg_x = sum_x / avg_count
        avg_y = sum_y / avg_count
        avg_z = sum_z / avg_count
        avg_temp = sum_temp / avg_count

        # decide whether we also log real time
        if (sync_time_ms is not None) and (sync_tick is not None):
            # use center_tick for time
            dt = time.ticks_diff(center_tick, sync_tick)     # ms since sync
            current_time_ms = sync_time_ms + dt              # ms since 1970 from user device
            # line format: tick,x,y,z,temp,time_ms
            samples.append(f"{center_tick},{avg_x},{avg_y},{avg_z},{avg_temp},{current_time_ms}\n")
        else:
            # format before sync: tick,x,y,z,temp
            samples.append(f"{center_tick},{avg_x},{avg_y},{avg_z},{avg_temp}\n")

        # reset averaging window
        avg_count = 0
        sum_x = 0.0
        sum_y = 0.0
        sum_z = 0.0
        sum_temp = 0.0
        window_start_tick = None
        window_end_tick = None
    
    #flush to SD card periodically
    if len(samples) >= flush_every:
        f.write(''.join(samples))
        f.flush()
        samples.clear()
    
    #wait until the scheduled tick
    wait = time.ticks_diff(next_tick, time.ticks_ms())
    if wait > 0:
        time.sleep_ms(wait)
    
    return next_tick

#code from pico youtube video
def ap_setup():
    ap = network.WLAN(network.AP_IF)
    ap.config(ssid=ssid, password=password)
    ap.active(True)
    while not ap.active():
        print("connecting...")
        time.sleep(1)
    ip = ap.ifconfig()[0]
    print("connected! IP =", ip)
    return ip

def open_socket():
    address = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    s = socket.socket()
    s.bind(address)
    s.listen(3)
    return s

#websight, lets rewrite 
HTML = """<!DOCTYPE html>
<html>
<style>
  body {
    background-color: black;
    color: white;
    font-family: 'Courier New';
  }
  canvas {
    width:95%%;
    height:320px;
    background:#111;
    display:block;
    margin:auto;
  }
  .x{color:#f55}.y{color:#5f5}.z{color:#59f}
</style>

<h1>MAGNETOMETER</h1>

<hr style="border: 1px solid white;">

<!-- Buttons -->
<div style="display:flex;gap:10px;">
    <button id="live"
            style="background:#444;color:#fff;font-family:'Courier New';font-size:18px;">
        Live View
    </button>
    <button id="download"
            style="background:transparent;color:#fff;font-family:'Courier New';font-size:18px;">
        Download Data
    </button>
</div>

<!-- Graph + overlay box -->
<div id="graph" style="position:relative;border:1px solid #ccc;height:320px;background:black;">
  <canvas id="c" width="720" height="320"
          style="width:100%%;height:100%%;background:#111;"></canvas>
  <!-- OPAQUE textbox over graph -->
  <div id="box"
       style="display:none;position:absolute;inset:0;
              background:white;color:black;
              font-family:'Courier New';font-size:16px;
              align-items:flex-start;justify-content:flex-start;
              padding:10px;overflow:auto;">
    <!-- file list will be injected here -->
  </div>
</div>

<p>
  <span class="x" id="x">x: –</span>,
  <span class="y" id="y">y: –</span>,
  <span class="z" id="z">z: –</span>
</p>

<script>
const live    = document.getElementById('live');
const download = document.getElementById('download');
const box     = document.getElementById('box');

// send browser time once when page loads (in ms)
fetch('/sync?time=' + Date.now()).catch(() => {});

// Live button: hide overlay, reset colors
live.onclick = () => {
  box.style.display = "none";
  live.style.background = "#444";
  download.style.background = "transparent";
};

// Download button: show overlay, load directory listing into it
download.onclick = async () => {
  live.style.background = "black";
  download.style.background = "#444";  // same grey as live
  box.style.display = "flex";
  box.innerHTML = "Loading SD card files...";

  try {
    const resp = await fetch('/download');
    const html = await resp.text();
    box.innerHTML = html;           // inject file list HTML
  } catch (e) {
    box.innerHTML = "Error loading file list.";
  }
};

// ----- Graph code (same logic as your working version) -----
let xs=[],ys=[],zs=[],N=120,MAX=250;
const ctx=c.getContext('2d');
function push(a,v){a.push(v);if(a.length>N)a.shift();}
function draw(){
  const all=xs.concat(ys,zs);
  if(!all.length) return;
  const mn=Math.min(...all),mx=Math.max(...all);
  ctx.clearRect(0,0,c.width,c.height);
  const map=y=>c.height-(y-mn)*c.height/(mx-mn||1);
  for(let i=0;i<=10;i++){
    let y=i*c.height/10,v=(mx-(mx-mn)*i/10).toFixed(1);
    ctx.strokeStyle='#222';ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(c.width,y);ctx.stroke();
    ctx.fillStyle='#888';ctx.fillText(v+' nT',2,y-2);
  }
  const line=(a,col)=>{
    ctx.strokeStyle=col;
    ctx.beginPath();
    a.forEach((v,i)=>ctx.lineTo(i*c.width/N,map(v)));
    ctx.stroke();
  };
  line(xs,'#f55');line(ys,'#5f5');line(zs,'#59f');
}
async function loop(){
  while(true){
    try{
      const d=await (await fetch('/data')).json();
      push(xs,d.x);push(ys,d.y);push(zs,d.z);
      if(xs.length>MAX){xs=[];ys=[];zs=[];} // clear memory when graph gets long
      x.textContent=`x: ${d.x.toFixed(1)} nT`;
      y.textContent=`y: ${d.y.toFixed(1)} nT`;
      z.textContent=`z: ${d.z.toFixed(1)} nT`;
      draw();
    }catch(e){}
    await new Promise(r=>setTimeout(r,300));
  }
}
loop();
</script>
</html>
"""
 


def webpage(state_str):
    return HTML  # no % formatting needed anymore

# main Loop
ip = ap_setup()
s = open_socket()
print("Open browser to http://" + ip)
s.settimeout(0.05)

x, y, z, temp = read_xyz()
print(f"X={x}, Y={y}, Z={z}, T={temp}")

#clear the SD card file before a new session
#with open("/sd/field_data.txt", "w") as f:
    #f.write("")  # empties the file
#print("SD card log cleared.")

log_f = open("/sd/field_data.txt", "a")
next_tick = None


try:
    while True:
        #use sampling function (this now does averaging + logging)
        next_tick = sample_100hz(log_f, flush_every=30, next_tick=next_tick)

        #try to connect with user via wifi
        try:
            client, addr = s.accept()
            client.settimeout(1)
        except OSError as e:
            # no client connected during this 50ms window; go back to logging
            continue

        request = client.recv(1024).decode()
        path = ""
        try:
            path = request.split(" ")[1]
        except Exception:
            pass

        if path == "/on":
            led.value(1)
            state = "ON"

        elif path == "/off":
            led.value(0)
            state = "OFF"

        elif path == "/data":
            x, y, z, temp = read_xyz()
            timestamp = time.time()
            session_data.append((timestamp, x, y, z, temp))

            if len(session_data) > 300:
                session_data = session_data[-300:]

            payload = json.dumps({"x": x, "y": y, "z": z})
            client.send("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n")
            client.send(payload)
            client.close()
            continue

        # sync endpoint to capture browser time once
        elif path.startswith("/sync?"):
            # path looks like: /sync?time=1733699999999
            try:
                query = path.split("?", 1)[1]
                for part in query.split("&"):
                    if part.startswith("time="):
                        sync_time_ms = int(part.split("=", 1)[1])
                        sync_tick = time.ticks_ms()
                        break
            except Exception:
                pass
            client.send("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nOK")
            client.close()
            continue

        elif path == "/download":
            try:
                files = uos.listdir("/sd")  #variable for the files on the SD card
            except OSError:
                files = []

            snippet = "<h2>SD Card Files</h2>\n"
            if not files:
                snippet += "<p>No files found on SD card.</p>\n" #if thereare no files, type this
            else:
                snippet += "<ul>\n"
                for name in files:
                    snippet += f'  <li><a href="/files/{name}">{name}</a></li>\n'
                snippet += "</ul>\n"

            client.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
            client.send(snippet)
            client.close()
            continue

        elif path.startswith("/files/"): 
            fname = path[len("/files/"):]
            full_path = "/sd/" + fname
            try:
                f = open(full_path, "rb")
            except OSError:
                client.send("HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nFile not found")
                client.close()
                continue
            #dowloan files
            client.send( 
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/octet-stream\r\n"
                f"Content-Disposition: attachment; filename={fname}\r\n\r\n"
            )
            while True:
                data = f.read(512)
                if not data:
                    break
                client.send(data)
            f.close()
            client.close()
            continue

        page = webpage(state)
        client.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
        client.send(page)
        client.close()

except OSError:
    try:
        client.close()
    except Exception:
        pass
    print("Error: connection closed")
