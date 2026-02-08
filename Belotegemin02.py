import random
import time
from flask import Flask, render_template_string, request, url_for
from flask_socketio import SocketIO, emit

app = Flask(__name__)
# Robust ping settings
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=30, ping_interval=5)

# --- CONSTANTS ---
SUITS_MAP = {"s": "spades", "c": "clubs", "d": "diamonds", "h": "hearts"}
RANKS_MAP = {"7":"seven","8":"eight","9":"nine","T":"ten","J":"jack","Q":"queen","K":"king","A":"ace"}
DEAL_ORDER = ["East", "North", "West", "South"]
RANK_VALS = {"7":0, "8":1, "9":2, "T":3, "J":4, "Q":5, "K":6, "A":7}

# Points
TRUMP_ORDER = ["J", "9", "A", "T", "K", "Q", "8", "7"]
NORMAL_ORDER = ["A", "T", "K", "Q", "J", "9", "8", "7"]
TRUMP_PTS = {"J": 20, "9": 14, "A": 11, "T": 10, "K": 4, "Q": 3, "8": 0, "7": 0}
NORMAL_PTS = {"A": 11, "T": 10, "K": 4, "Q": 3, "J": 2, "9": 0, "8": 0, "7": 0}

# --- STATE ---
game = {
    "seats": {}, 
    "dealer_idx": 0, "up_card": None, "trump": None, "trump_by": None,
    "bid_round": 1, "bidder_offset": 1, "player_idx": 0, "played_cards": [], 
    "trick_count": 0, "tricks_won_by": {"NS": 0, "EW": 0}, 
    "round_scores": {"NS": 0, "EW": 0}, "total_scores": {"NS": 0, "EW": 0}, 
    "deck": [], "in_progress": False, 
    "belote_status": {p: False for p in DEAL_ORDER}, "hands": {p: [] for p in DEAL_ORDER}, 
    "last_trick": []
}

def get_card_filename(code):
    return f"{RANKS_MAP[code[0]]}-of-{SUITS_MAP[code[1]]}.gif"

def check_sequences(hand):
    pts, names = 0, []
    for s_key in SUITS_MAP.keys():
        indices = sorted([RANK_VALS[c[0]] for c in hand if c[1] == s_key])
        if not indices: continue
        count, best = 1, 1
        for i in range(len(indices)-1):
            if indices[i+1] == indices[i] + 1:
                count += 1
                best = max(best, count)
            else: count = 1
        if best == 3: pts += 20; names.append("Tierce")
        elif best == 4: pts += 50; names.append("Fifty")
        elif best >= 5: pts += 100; names.append("Hundred")
    return pts, names

def get_best_card(played, trump):
    if not played: return None
    lead = played[0]
    best = lead
    for c in played[1:]:
        if c['suit'] == trump:
            if best['suit'] != trump or TRUMP_ORDER.index(c['rank']) < TRUMP_ORDER.index(best['rank']):
                best = c
        elif c['suit'] == lead['suit'] and best['suit'] != trump:
            if NORMAL_ORDER.index(c['rank']) < NORMAL_ORDER.index(best['rank']):
                best = c
    return best

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@socketio.on("connect")
def handle_connect():
    sid = request.sid
    if len(game["seats"]) >= 4:
        emit("notification", "Game Full (4/4)", to=sid)
        return

    for seat in DEAL_ORDER:
        if seat not in game["seats"].values():
            game["seats"][sid] = seat
            count = len(game["seats"])
            emit("assign_seat", {"seat": seat, "dealer": DEAL_ORDER[game["dealer_idx"]], "connected": count})
            emit("update_count", {"count": count}, broadcast=True)
            return
    
    game["seats"][sid] = "Observer"
    emit("assign_seat", {"seat": "Observer", "dealer": DEAL_ORDER[game["dealer_idx"]], "connected": len(game["seats"])})

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    if sid in game["seats"]:
        del game["seats"][sid]
        emit("update_count", {"count": len(game["seats"])}, broadcast=True)

@socketio.on("start_game")
def start_game():
    seat = game["seats"].get(request.sid)
    if seat != DEAL_ORDER[game["dealer_idx"]] or (game["in_progress"] and game["trick_count"] < 8): return
    
    if any(v >= 1001 for v in game["total_scores"].values()): game["total_scores"] = {"NS": 0, "EW": 0}
    
    full_deck = [f"{r}{s}" for r in RANKS_MAP.keys() for s in SUITS_MAP.keys()]
    random.shuffle(full_deck)
    
    game.update({"up_card": full_deck.pop(), "trump": None, "trump_by": None, "bid_round": 1, "bidder_offset": 1, 
                 "trick_count": 0, "tricks_won_by": {"NS": 0, "EW": 0}, "played_cards": [], 
                 "round_scores": {"NS": 0, "EW": 0}, "in_progress": True, "belote_status": {p: False for p in DEAL_ORDER},
                 "last_trick": []})
    
    emit("clear_all", broadcast=True)
    for sid, s_name in game["seats"].items():
        if s_name == "Observer": continue
        game["hands"][s_name] = [full_deck.pop() for _ in range(5)]
        game["hands"][s_name].sort(key=lambda x: RANK_VALS[x[0]], reverse=True)
        emit("receive_hand", {"filenames": [get_card_filename(c) for c in game["hands"][s_name]]}, to=sid)
    game["deck"] = full_deck
    emit("show_up_card", {"card": get_card_filename(game["up_card"]), "suit": SUITS_MAP[game["up_card"][1]], "round": 1, "bidder": DEAL_ORDER[(game["dealer_idx"]+1)%4], "dealer": DEAL_ORDER[game["dealer_idx"]]}, broadcast=True)

@socketio.on('make_bid')
def handle_bid(data):
    decision, seat = data['decision'], data['seat']
    if decision == 'take' or decision in SUITS_MAP.values():
        game["trump"] = SUITS_MAP[game["up_card"][1]] if decision == 'take' else decision
        game["trump_by"] = seat
        game["taker_team"] = "NS" if seat in ["North", "South"] else "EW"
        game["player_idx"] = (game["dealer_idx"] + 1) % 4
        
        for s_name in DEAL_ORDER:
            extra = [game["deck"].pop() for _ in range(2 if s_name == seat else 3)]
            if s_name == seat: extra.append(game["up_card"])
            game["hands"][s_name].extend(extra)
            game["hands"][s_name].sort(key=lambda x: (0 if SUITS_MAP[x[1]] == game["trump"] else 1, x[1], RANK_VALS[x[0]]))
            
            pts, names = check_sequences(game["hands"][s_name])
            t_sid = next((sid for sid, name in game["seats"].items() if name == s_name), None)
            if t_sid and pts > 0: emit("ask_declaration", {"names": names, "pts": pts}, to=t_sid)
            if t_sid: emit("receive_extra", {"filenames": [get_card_filename(c) for c in game["hands"][s_name]], "trump": game["trump"]}, to=t_sid)
            
        emit("trump_confirmed", {"suit": game["trump"], "by": seat, "sound": True}, broadcast=True)
        emit("sync_turn", {"active": DEAL_ORDER[game["player_idx"]]}, broadcast=True)
    else:
        game["bidder_offset"] += 1
        if game["bidder_offset"] > 4:
            if game["bid_round"] == 1:
                # Rule 65: Jack Pass Halt - Center Notification
                if game["up_card"][0] == 'J':
                    game["dealer_idx"] = (game["dealer_idx"] + 1) % 4
                    game["in_progress"] = False
                    emit("game_halt", {"msg": "Jack passed 4 times. New Deal required.", "next_dealer": DEAL_ORDER[game["dealer_idx"]]}, broadcast=True)
                else:
                    game["bid_round"], game["bidder_offset"] = 2, 1
                    emit("show_up_card", {"card": get_card_filename(game["up_card"]), "suit": SUITS_MAP[game["up_card"][1]], "round": 2, "bidder": DEAL_ORDER[(game["dealer_idx"]+1)%4], "dealer": DEAL_ORDER[game["dealer_idx"]]}, broadcast=True)
            else:
                game["dealer_idx"] = (game["dealer_idx"] + 1) % 4
                game["in_progress"] = False
                emit("game_halt", {"msg": "No trump chosen. New Deal.", "next_dealer": DEAL_ORDER[game["dealer_idx"]]}, broadcast=True)
        else:
            nb = DEAL_ORDER[(game["dealer_idx"] + game["bidder_offset"]) % 4]
            emit("show_up_card", {"card": get_card_filename(game["up_card"]), "suit": SUITS_MAP[game["up_card"][1]], "round": game["bid_round"], "bidder": nb, "dealer": DEAL_ORDER[game["dealer_idx"]]}, broadcast=True)

@socketio.on('declare')
def handle_declare(data):
    team = "NS" if game["seats"].get(request.sid) in ["North", "South"] else "EW"
    game["round_scores"][team] += data['pts']
    emit("game_message", {"msg": f"{game['seats'].get(request.sid)} declared {', '.join(data['names'])}!"}, broadcast=True)

@socketio.on('play_card')
def handle_play(data):
    sid = request.sid
    seat = game["seats"].get(sid)
    
    # Rule 62: Cannot play before trump selection
    if game["trump"] is None:
        emit("notification", "Wait for trump selection!", to=sid)
        return

    if seat == "Observer" or seat != DEAL_ORDER[game["player_idx"]]: 
        return

    card_file = data['card']
    s_str = card_file.split('-of-')[1].split('.')[0]
    r_code = [k for k, v in RANKS_MAP.items() if v == card_file.split('-of-')[0]][0]
    hand = game["hands"][seat]

    current_hand_files = [get_card_filename(c) for c in hand]
    if card_file not in current_hand_files: return

    # --- RULES VALIDATION ---
    if game["played_cards"]:
        lead_card = game["played_cards"][0]
        lead_s = lead_card['suit']
        has_lead = any(SUITS_MAP[c[1]] == lead_s for c in hand)
        has_trump = any(SUITS_MAP[c[1]] == game["trump"] for c in hand)
        
        # Rule 24: Suit Follow - Center Notification
        if has_lead and s_str != lead_s:
            emit("notification", "Must follow lead suit!", to=sid)
            return

        current_winner = get_best_card(game["played_cards"], game["trump"])
        partner = {"North":"South","South":"North","East":"West","West":"East"}[seat]
        partner_winning = (current_winner['seat'] == partner)

        if not has_lead:
            # Rule 28: Must trump if partner not winning
            if not partner_winning and has_trump and s_str != game["trump"]:
                emit("notification", "Must play a trump!", to=sid)
                return
            
            # Rule 50: Overtrump
            if s_str == game["trump"]:
                trumps_played = [c for c in game["played_cards"] if c['suit'] == game["trump"]]
                if trumps_played:
                    best_t_rank = min([TRUMP_ORDER.index(c['rank']) for c in trumps_played])
                    can_overtrump = any(SUITS_MAP[c[1]] == game["trump"] and TRUMP_ORDER.index(c[0]) < best_t_rank for c in hand)
                    if not partner_winning and can_overtrump and TRUMP_ORDER.index(r_code) >= best_t_rank:
                        emit("notification", "Must overtrump!", to=sid)
                        return

        if s_str == game["trump"] and lead_s == game["trump"]:
             trumps_played = [c for c in game["played_cards"] if c['suit'] == game["trump"]]
             if trumps_played:
                best_t_rank = min([TRUMP_ORDER.index(c['rank']) for c in trumps_played])
                can_overtrump = any(SUITS_MAP[c[1]] == game["trump"] and TRUMP_ORDER.index(c[0]) < best_t_rank for c in hand)
                if can_overtrump and TRUMP_ORDER.index(r_code) >= best_t_rank:
                    emit("notification", "Must overtrump!", to=sid)
                    return

    # --- Rule 63: Strict Belote Logic ---
    if s_str == game["trump"] and r_code in ['K', 'Q']:
        if not game["belote_status"][seat]:
            # This is the FIRST card of the pair played.
            # Do I hold the matching pair in my hand RIGHT NOW?
            matching_rank = 'Q' if r_code == 'K' else 'K'
            has_pair = any(c[0] == matching_rank and SUITS_MAP[c[1]] == game["trump"] for c in hand)
            
            if has_pair:
                game["belote_status"][seat] = True
                emit("game_message", {"msg": f"{seat}: BELOTE!", "sound": "belote"}, broadcast=True)
        else:
            # Belote already declared
            game["round_scores"]["NS" if seat in ["North", "South"] else "EW"] += 20
            emit("game_message", {"msg": f"{seat}: REBLOTE!", "anim": "reblote", "sound": "reblote"}, broadcast=True)

    game["played_cards"].append({"seat": seat, "file": card_file, "rank": r_code, "suit": s_str})
    game["hands"][seat] = [c for c in game["hands"][seat] if get_card_filename(c) != card_file]
    emit("receive_hand", {"filenames": [get_card_filename(c) for c in game["hands"][seat]]}, to=sid)
    
    current_win = get_best_card(game["played_cards"], game["trump"])
    trump_led = (game["played_cards"][0]['suit'] == game["trump"])
    emit("animate_card", {"card": card_file, "seat": seat, "winner_file": current_win['file'], "trump_lead": trump_led}, broadcast=True)

    if len(game["played_cards"]) == 4:
        winner = current_win
        pts = sum(TRUMP_PTS.get(c['rank'], 0) if c['suit'] == game["trump"] else NORMAL_PTS.get(c['rank'], 0) for c in game["played_cards"])
        team = "NS" if winner['seat'] in ["North", "South"] else "EW"
        game["round_scores"][team] += pts
        game["trick_count"] += 1
        game["tricks_won_by"][team] += 1
        game["player_idx"] = DEAL_ORDER.index(winner['seat'])
        
        if game["trick_count"] == 8:
            game["round_scores"][team] += 10
            emit("game_message", {"msg": f"10 de der (+10) to {winner['seat']}!", "indicator": "10der"}, broadcast=True)
            
        emit("trick_end", {"winner": winner['seat'], "pts": pts, "files": [c['file'] for c in game["played_cards"]], "ns": game["round_scores"]["NS"], "ew": game["round_scores"]["EW"], "trick_num": game["trick_count"]}, broadcast=True)
        
        game["last_trick"] = [c['file'] for c in game["played_cards"]]
        game["played_cards"] = []
        
        if game["trick_count"] == 8:
            socketio.sleep(1.5)
            finalize_round(team)
        else:
            emit("sync_turn", {"active": winner['seat']}, broadcast=True)
    else:
        game["player_idx"] = (game["player_idx"] + 1) % 4
        emit("sync_turn", {"active": DEAL_ORDER[game["player_idx"]]}, broadcast=True)

def finalize_round(win_team):
    if game["tricks_won_by"][win_team] == 8: 
        game["round_scores"][win_team] = 250
        game["round_scores"]["NS" if win_team == "EW" else "EW"] = 0
    
    for t in ["NS", "EW"]: 
        game["total_scores"][t] += game["round_scores"][t]
    
    game["in_progress"], game["dealer_idx"] = False, (game["dealer_idx"] + 1) % 4
    
    emit("show_summary", {
        "round": game["round_scores"], 
        "total": game["total_scores"], 
        "dealer": DEAL_ORDER[game["dealer_idx"]], 
        "is_over": any(v >= 1001 for v in game["total_scores"].values())
    }, broadcast=True)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Belote Master 1001</title>
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div id="flash" class="flash">REBLOTE!</div>
    <div id="decl-menu"><h3>Announce sequences?</h3><div id="decl-list" style="margin-bottom:15px; color: gold;"></div><button id="btn-decl-yes">YES (Announce)</button> <button onclick="document.getElementById('decl-menu').style.display='none'">HIDE</button></div>
    
    <div id="center-notification"></div>

    <div id="summary">
        <h1 id="sum-title" style="color:gold; font-size: 3em;">ROUND OVER</h1>
        <div id="sum-scores" style="font-size: 1.8em; margin: 20px; color: white;"></div>
        <button id="redeal-btn" onclick="socket.emit('start_game')">START NEXT DEAL</button>
    </div>

    <div style="display:flex; flex-direction:row; height:100vh;">
        <div class="main">
            <div id="top-bar">
                <div id="trump-indicator"></div>
                <div id="ui-score">NS: 0 | EW: 0</div>
                <div id="turn-indicator"></div>
            </div>
            
            <div id="msg">Connecting...</div>
            
            <div class="table">
                <div id="last-trick"></div>
                <div class="felt">
                    <div id="ui-dealer"></div>
                    <div id="play-zone"></div>
                    <div id="center-trump"></div>
                    <div id="up-card" style="position:absolute; top:35%; left:45%;"></div>
                    <div id="my-seat"></div>
                    <button id="deal-btn" onclick="socket.emit('start_game')">DEAL HAND</button>
                </div>
                <div id="bidding"></div>
            </div>
            <div id="hand-area"></div>
        </div>

        <div class="sidebar">
            <div id="history-header">
                <div>HISTORY</div>
                <div style="font-size:0.8em; color:cyan; margin-top:5px;">Dealer: <span id="ui-dealer-side">...</span></div>
                <div style="font-size:0.8em; color:lime;">Trick: <span id="ui-trick">1/8</span></div>
            </div>
            <div id="history"></div>
        </div>
    </div>

    <script>
        var socket = io(); var mySeat = "", activeP = "", leadS = "";
        const SYMBOLS = {spades:'&spades;', clubs:'&clubs;', diamonds:'&diams;', hearts:'&hearts;'};
        
        // Sounds
        const sndPlay = new Audio('https://actions.google.com/sounds/v1/foley/paper_shuffle.ogg');
        const sndWin = new Audio('https://actions.google.com/sounds/v1/cartoon/pop.ogg');
        const sndTrump = new Audio('https://actions.google.com/sounds/v1/cartoon/clime.ogg');
        const sndBelote = new Audio('https://actions.google.com/sounds/v1/cartoon/cowbell.ogg');

        function playSound(snd) {
            snd.play().catch(e => console.log("Sound blocked by browser:", e));
        }

        // Rule 64: Notification Helper
        function showNotification(text, color="#ff4757") {
            const el = document.getElementById('center-notification');
            el.innerText = text;
            el.style.color = color;
            el.style.display = "block";
            // Flash animation
            el.style.opacity = 1;
            setTimeout(() => { el.style.display = "none"; }, 3000);
        }

        socket.on('notification', msg => showNotification(msg));

        socket.on('assign_seat', d => { 
            mySeat = d.seat; 
            document.getElementById('ui-dealer').innerText = "Dealer: " + d.dealer;
            document.getElementById('ui-dealer-side').innerText = d.dealer;
            document.getElementById('my-seat').innerText = "ME: " + d.seat;
            document.getElementById('deal-btn').style.display = (mySeat === d.dealer) ? "block" : "none";
            document.getElementById('msg').innerText = d.connected + "/4 Ready";
        });
        
        socket.on('update_count', d => { document.getElementById('msg').innerText = d.count + "/4 Ready"; });

        socket.on('receive_hand', d => { 
            renderHand(d.filenames); 
            document.getElementById('deal-btn').style.display="none"; 
            document.getElementById('summary').style.display="none"; 
            document.getElementById('center-trump').style.display="none";
            document.getElementById('msg').style.color="gold"; 
        });
        socket.on('receive_extra', d => { renderHand(d.filenames); });

        function updateHighlights() {
            const isMyTurn = (activeP === mySeat);
            document.querySelectorAll('.card-img').forEach(img => {
                const s = img.src.split('-of-')[1].split('.')[0];
                let isValid = true;
                if (isMyTurn && leadS) {
                    const hasLead = Array.from(document.querySelectorAll('.card-img')).some(c => c.src.includes(leadS));
                    if (s !== leadS && hasLead) isValid = false;
                }
                if (!isMyTurn) img.className = "card-img"; 
                else img.className = "card-img" + (isValid ? " valid" : " invalid");
            });
        }

        function renderHand(files) {
            const area = document.getElementById('hand-area'); area.innerHTML = "";
            files.forEach((f, i) => {
                let img = document.createElement('img'); img.src = "/static/cards/"+f; img.className = "card-img";
                img.style.left = `calc(50% + ${(i - files.length/2)*60}px - 50px)`;
                img.onclick = () => { if(activeP === mySeat) socket.emit('play_card', {card: f}); };
                area.appendChild(img);
            });
            updateHighlights();
        }

        socket.on('ask_declaration', d => {
            const menu = document.getElementById('decl-menu'); menu.style.display = 'block';
            document.getElementById('decl-list').innerText = d.names.join(", ") + " (" + d.pts + " pts)";
            document.getElementById('btn-decl-yes').onclick = () => { socket.emit('declare', d); menu.style.display = 'none'; };
        });

        socket.on('animate_card', d => {
            playSound(sndPlay);
            if(document.getElementById('play-zone').children.length === 0) leadS = d.card.split('-of-')[1].split('.')[0];
            let img = document.createElement('img'); img.src = "/static/cards/"+d.card; img.className = "played-card";
            img.dataset.file = d.card;
            const pos = {"North":"top:10px;left:45%", "South":"bottom:70px;left:45%", "East":"right:10px;top:35%", "West":"left:10px;top:35%"};
            img.style.cssText += pos[d.seat]; document.getElementById('play-zone').appendChild(img);
            
            document.querySelectorAll('.played-card').forEach(c => c.classList.remove('winning-glow'));
            const winningCardEl = document.querySelector(`[data-file="${d.winner_file}"]`);
            if(winningCardEl) winningCardEl.classList.add('winning-glow');
            
            if(d.trump_lead) document.getElementById('trump-indicator').classList.add('pulse');
            else document.getElementById('trump-indicator').classList.remove('pulse');
            
            updateHighlights();
        });

        socket.on('show_up_card', d => {
            activeP = d.bidder; document.getElementById('msg').innerText = "BIDDING: " + d.bidder;
            document.getElementById('up-card').innerHTML = `<img src="/static/cards/${d.card}" width="85" style="border:2px solid gold;">`;
            const bid = document.getElementById('bidding'); bid.style.display = (mySeat === d.bidder) ? "block" : "none";
            if(mySeat === d.bidder) {
                if(d.round === 1) bid.innerHTML = `<button onclick="socket.emit('make_bid',{decision:'take',seat:mySeat})">TAKE ${d.suit.toUpperCase()}</button> <button onclick="socket.emit('make_bid',{decision:'pass',seat:mySeat})">PASS</button>`;
                else {
                    let h = ""; 
                    for(let s in SYMBOLS) if(s !== d.suit) h += `<button class="bid-btn ${s}" onclick="socket.emit('make_bid', {decision:'${s}', seat:mySeat})">${SYMBOLS[s]}</button> `;
                    if(mySeat !== d.dealer) h += `<button onclick="socket.emit('make_bid',{decision:'pass',seat:mySeat})">PASS</button>`;
                    bid.innerHTML = h;
                }
            }
        });

        socket.on('trump_confirmed', d => {
            if(d.sound) playSound(sndTrump);
            const ind = document.getElementById('trump-indicator'); ind.style.display = "block";
            ind.innerHTML = `Trump: ${SYMBOLS[d.suit]} by ${d.by}`;
            
            const ct = document.getElementById('center-trump');
            ct.style.display = "block";
            ct.innerHTML = SYMBOLS[d.suit];
            ct.style.color = (d.suit === 'hearts' || d.suit === 'diamonds') ? '#ff4757' : '#000000';
            
            document.getElementById('up-card').innerHTML = ""; document.getElementById('bidding').innerHTML = "";
        });

        socket.on('game_message', d => {
            if(d.anim) { let f = document.getElementById('flash'); f.style.display = "block"; setTimeout(()=>f.style.display="none", 1500); playSound(sndBelote); }
            let color = d.indicator === "10der" ? "gold" : "lime";
            let h = document.getElementById('history');
            h.innerHTML += `<div style="color:${color}">> ${d.msg}</div>`;
            h.scrollTop = h.scrollHeight;
        });

        socket.on('trick_end', d => {
            playSound(sndWin);
            setTimeout(() => { document.getElementById('play-zone').innerHTML = ""; leadS = ""; updateHighlights(); document.getElementById('trump-indicator').classList.remove('pulse'); }, 1200);
            let lt = document.getElementById('last-trick'); lt.style.display = "block"; lt.innerHTML = "";
            d.files.forEach(f => lt.innerHTML += `<img src="/static/cards/${f}" width="25">`);
            document.getElementById('ui-score').innerText = `NS: ${d.ns} | EW: ${d.ew}`;
            document.getElementById('ui-trick').innerText = (parseInt(d.trick_num) < 8) ? (parseInt(d.trick_num) + 1) + "/8" : "8/8";
            
            let h = document.getElementById('history');
            h.innerHTML += `<div style="color:cyan; margin-top:5px; border-bottom:1px solid #333; padding-bottom:2px;">Trick Won by ${d.winner} (+${d.pts} pts)</div>`;
            h.scrollTop = h.scrollHeight;
        });

        socket.on('show_summary', d => {
            const s = document.getElementById('summary'); s.style.display = "flex";
            document.getElementById('redeal-btn').style.display = (mySeat === d.dealer) ? "block" : "none";
            if(d.is_over) { document.getElementById('sum-title').innerText = "TOURNAMENT OVER"; }
            document.getElementById('sum-scores').innerHTML = `ROUND: NS ${d.round.NS} - EW ${d.round.EW}<br>TOTAL: NS ${d.total.NS} - EW ${d.total.EW}`;
            document.getElementById('scoreboard').style.background = d.total.NS > d.total.EW ? "#002b5c" : "#5c0000";
        });

        socket.on('game_halt', d => { 
            // Rule 65: Halt message center table
            showNotification(d.msg, "#ffcc00");
            const msgEl = document.getElementById('msg');
            msgEl.innerText = "NEW DEAL REQ. Next: " + d.next_dealer; 
            msgEl.style.color = "#ff4757"; 
            document.getElementById('deal-btn').style.display = (mySeat === d.next_dealer) ? "block" : "none"; 
        });

        socket.on('sync_turn', d => { 
            activeP = d.active; 
            document.getElementById('msg').innerText = "Turn: "+d.active; 
            document.getElementById('turn-indicator').innerText = "TURN: " + d.active;
            document.getElementById('turn-indicator').style.display = "block";
            updateHighlights(); 
        });
        
        socket.on('clear_all', () => { 
            document.getElementById('play-zone').innerHTML = ""; 
            document.getElementById('history').innerHTML = ""; 
            document.getElementById('trump-indicator').style.display="none"; 
            document.getElementById('turn-indicator').style.display="none";
            document.getElementById('last-trick').innerHTML = ""; 
            document.getElementById('ui-trick').innerText="1/8";
            document.getElementById('center-trump').style.display="none";
        });
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
