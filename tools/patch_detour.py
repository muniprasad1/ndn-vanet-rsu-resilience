import sys
p = sys.argv[1]; s = open(p).read(); n = 0
def rep(old, new):
    global s, n
    if s.count(old) != 1: sys.exit(f"STOPPED, nothing changed: not found exactly once:\n{old[:120]}")
    s = s.replace(old, new); n += 1

# A. detour helpers
rep('// ---- Traffic-information content (all ODDs) ------------------------------\n',
'// ---- Routing around failed RSUs (2-D ODDs) ---------------------------------\n'
'// Routes are computed once at start. Whenever backbone links fail or come back, each\n'
'// RSU checks its routes to NON-neighbour RSUs: a route is kept only if its next hop is\n'
'// healthy AND one hop closer to the destination over healthy links; otherwise it moves\n'
'// to such a neighbour (every hop gets strictly closer -> no loops). The original route\n'
'// returns once it passes the same test. Neighbour routes stay with the VCF ferries;\n'
'// destinations with no healthy path (e.g. the failed RSU itself) go to the transit ferry.\n'
'bool g_detourEnabled = true;\n'
'std::map<std::pair<uint32_t,uint32_t>, NetDeviceContainer>* g_primaryLinksPtr = nullptr;\n'
'std::vector<std::pair<uint32_t,uint32_t>>* g_rsuPairsPtr = nullptr;\n'
'NodeContainer* g_rsuNodesPtr = nullptr;\n'
'const std::vector<RsuListEntry>* g_rsuListPtr = nullptr;\n'
'std::map<std::pair<uint32_t,uint32_t>, uint32_t> g_detourOrig;  // (rsu, dest) -> original next hop\n'
'\n'
'static bool PairUp(uint32_t a, uint32_t b) {\n'
'  const auto& L = *g_rsuListPtr;\n'
'  return g_pairDown.count({L[a].id, L[b].id}) == 0;\n'
'}\n'
'static Ptr<NetDevice> PrimaryDev(uint32_t a, uint32_t b) {   // device on RSU a towards neighbour b\n'
'  auto it = g_primaryLinksPtr->find({std::min(a, b), std::max(a, b)});\n'
'  if (it == g_primaryLinksPtr->end()) return nullptr;\n'
'  return (a < b) ? it->second.Get(0) : it->second.Get(1);\n'
'}\n'
'void RerouteAroundFailures() {\n'
'  if (!g_detourEnabled || g_rsuPairsPtr == nullptr) return;\n'
'  uint32_t n = g_rsuListPtr->size(), moved = 0, restored = 0;\n'
'  std::vector<std::vector<uint32_t>> adj(n), allNb(n);\n'
'  for (auto& pr : *g_rsuPairsPtr) {\n'
'    allNb[pr.first].push_back(pr.second); allNb[pr.second].push_back(pr.first);\n'
'    if (PairUp(pr.first, pr.second)) { adj[pr.first].push_back(pr.second); adj[pr.second].push_back(pr.first); }\n'
'  }\n'
'  std::vector<std::vector<int>> dist(n, std::vector<int>(n, -1));   // dist[d][x]: healthy hops x -> d\n'
'  for (uint32_t d = 0; d < n; d++) {\n'
'    std::vector<uint32_t> q{d}; dist[d][d] = 0;\n'
'    for (size_t k = 0; k < q.size(); k++)\n'
'      for (uint32_t v : adj[q[k]]) if (dist[d][v] < 0) { dist[d][v] = dist[d][q[k]] + 1; q.push_back(v); }\n'
'  }\n'
'  for (uint32_t a = 0; a < n; a++) {\n'
'    Ptr<Node> node = g_rsuNodesPtr->Get(a);\n'
'    Ptr<ndn::L3Protocol> l3 = node->GetObject<ndn::L3Protocol>();\n'
'    std::map<uint64_t, uint32_t> faceToNb;                            // this RSU: face id -> neighbour\n'
'    std::set<uint32_t> isNb(allNb[a].begin(), allNb[a].end());\n'
'    for (uint32_t b : allNb[a]) {\n'
'      Ptr<NetDevice> dev = PrimaryDev(a, b);\n'
'      auto f = (dev != nullptr) ? l3->getFaceByNetDevice(dev) : nullptr;\n'
'      if (f != nullptr) faceToNb[f->getId()] = b;\n'
'    }\n'
'    for (uint32_t d = 0; d < n; d++) {\n'
'      if (d == a || isNb.count(d)) continue;                          // neighbour routes: VCF ferries\n'
'      int da = dist[d][a];\n'
'      if (da <= 0) continue;                                          // no healthy path: transit ferry\n'
'      auto ok = [&](uint32_t v) { return PairUp(a, v) && dist[d][v] == da - 1; };\n'
'      std::string prefix = "/traffic/update/rsu" + std::to_string(d);\n'
'      auto key = std::make_pair(a, d);\n'
'      auto od = g_detourOrig.find(key);\n'
'      if (od != g_detourOrig.end() && ok(od->second)) {              // original route valid again\n'
'        SetSoleRoute(node, prefix, PrimaryDev(a, od->second), "DETOUR-END");\n'
'        g_detourOrig.erase(od); restored++; continue;\n'
'      }\n'
'      const nfd::fib::Entry& e = l3->getForwarder()->getFib().findLongestPrefixMatch(ndn::Name(prefix));\n'
'      int cur = -1;\n'
'      for (const auto& nh : e.getNextHops()) {\n'
'        auto it = faceToNb.find(nh.getFace().getId());\n'
'        if (it != faceToNb.end()) { cur = (int)it->second; break; }\n'
'      }\n'
'      if (cur < 0 || ok((uint32_t)cur)) continue;                     // not a backbone route, or still good\n'
'      uint32_t best = UINT32_MAX;\n'
'      for (uint32_t v : adj[a]) if (dist[d][v] == da - 1 && v < best) best = v;\n'
'      if (best == UINT32_MAX) continue;\n'
'      if (!g_detourOrig.count(key)) g_detourOrig[key] = (uint32_t)cur;\n'
'      SetSoleRoute(node, prefix, PrimaryDev(a, best), "DETOUR");\n'
'      moved++;\n'
'    }\n'
'  }\n'
'  if (moved || restored)\n'
'    std::cout << "[DETOUR-SUMMARY] t=" << Simulator::Now().GetSeconds() << "s: " << moved\n'
'              << " routes moved around failed links, " << restored << " restored" << std::endl;\n'
'}\n'
'void ScheduleDetourCheck(double t) {\n'
'  static std::set<double> done;\n'
'  if (done.insert(t).second) Simulator::Schedule(Seconds(t), &RerouteAroundFailures);\n'
'}\n'
'\n'
'// ---- Traffic-information content (all ODDs) ------------------------------\n')

# B. wire the pointers once the backbone exists
rep('  PreCreateCandidateLinks(candidateLinks, rsuNodeById, vehicleNodes, p2p);\n',
    '  g_primaryLinksPtr = &primaryLinks; g_rsuPairsPtr = &rsuPairs;\n'
    '  g_rsuNodesPtr = &rsuNodes; g_rsuListPtr = &rsuList;\n'
    '  PreCreateCandidateLinks(candidateLinks, rsuNodeById, vehicleNodes, p2p);\n')

# C. check routes just after each failure starts and after each repair
rep('      Simulator::Schedule(Seconds(w.second + 0.1), &RestorePairAfterFailure,\n'
    '                           i, j, primaryLinks[{i, j}]);\n',
    '      Simulator::Schedule(Seconds(w.second + 0.1), &RestorePairAfterFailure,\n'
    '                           i, j, primaryLinks[{i, j}]);\n'
    '      ScheduleDetourCheck(w.first + 0.01);\n'
    '      ScheduleDetourCheck(w.second + 0.2);\n')

# D. switch
rep('  cmd.AddValue("rangeBoost", "enable the range-boost fallback (baseline: false)", g_rangeBoostEnabled);\n',
    '  cmd.AddValue("rangeBoost", "enable the range-boost fallback (baseline: false)", g_rangeBoostEnabled);\n'
    '  cmd.AddValue("detour", "route around failed RSU links when a healthy path exists", g_detourEnabled);\n')
open(p, "w").write(s); print(f"PATCHED OK: {n} changes")
