from config.settings import SELECTION_WEIGHTS, STATIC_MAPPING, SERVERS

class ServerSelector:
    def __init__(self, cdn_mode="dynamic"):
        self.cdn_mode = cdn_mode
        self.weights = SELECTION_WEIGHTS

    def select_server(self, client_id, telemetry):
        if self.cdn_mode == "static":
            return SERVERS[STATIC_MAPPING.get(client_id, "srv1")]

        available = {k: v for k, v in telemetry.items() if v.get('status', 'UP') == 'UP'}
        if not available: return SERVERS['srv1']

        rtts = [d.get('rtt_ms', 50.0) for d in available.values()]
        conns = [d.get('active_conns', 0) for d in available.values()]
        min_rtt, max_rtt = min(rtts), max(rtts)
        min_c, max_c = min(conns), max(conns)
        eps = 1e-6

        best_id, lowest_score = None, float('inf')
        for s_id, d in available.items():
            rtt = d.get('rtt_ms', 50.0)
            util = min(1.0, max(0.0, d.get('utilization', 0.0)))
            conn = d.get('active_conns', 0)

            norm_lat = (rtt - min_rtt) / ((max_rtt - min_rtt) + eps) if max_rtt > min_rtt else 0.0
            norm_load = (conn - min_c) / ((max_c - min_c) + eps) if max_c > min_c else 0.0

            score = (self.weights['latency'] * norm_lat + self.weights['utilization'] * util + self.weights['load'] * norm_load)
            if score < lowest_score:
                lowest_score = score
                best_id = s_id

        return SERVERS[best_id]
