/**
 * Claude Code Changelog Observatory - Main Application Logic
 * Interactive Visualizations, Search, Filtering, Diff Comparator & Live Sync
 */

(function () {
  'use strict';

  // State Management
  const state = {
    insights: null,
    changelog: null,
    activeTab: 'tab-overview',
    searchQuery: '',
    selectedTag: 'all',
    selectedAction: 'all',
    visibleVersionLimit: 25,
    theme: document.documentElement.getAttribute('data-theme') || 'dark',
    charts: {}
  };

  // DOM Elements
  const elements = {
    tabs: document.querySelectorAll('.tab-btn'),
    sections: document.querySelectorAll('.view-section'),
    themeToggle: document.getElementById('theme-toggle'),
    btnTriggerUpdate: document.getElementById('btn-trigger-update'),
    btnManualSync: document.getElementById('btn-manual-sync'),
    updateBtnLabel: document.getElementById('update-btn-label'),
    syncStatusText: document.getElementById('sync-status-text'),
    manualSyncFeedback: document.getElementById('manual-sync-feedback'),
    headerVersionTag: document.getElementById('header-version-tag'),

    // Hero KPIs
    kpiTotalVersions: document.getElementById('kpi-total-versions'),
    kpiTotalItems: document.getElementById('kpi-total-items'),
    kpiLatestVer: document.getElementById('kpi-latest-ver'),
    kpiLatestDate: document.getElementById('kpi-latest-date'),
    kpiHighImpact: document.getElementById('kpi-high-impact'),

    // Containers
    pillarsContainer: document.getElementById('pillars-container'),
    gamechangersContainer: document.getElementById('gamechangers-container'),
    versionsContainer: document.getElementById('versions-container'),
    loadMoreContainer: document.getElementById('load-more-box'),
    btnLoadMore: document.getElementById('btn-load-more'),
    resultsCountText: document.getElementById('results-count-text'),
    btnToggleAllCards: document.getElementById('btn-toggle-all-cards'),
    searchInput: document.getElementById('search-input'),
    btnClearSearch: document.getElementById('btn-clear-search'),
    tagChips: document.querySelectorAll('[data-filter-tag]'),
    actionChips: document.querySelectorAll('[data-filter-action]'),

    // Diff tool
    selectVersionA: document.getElementById('select-version-a'),
    selectVersionB: document.getElementById('select-version-b'),
    btnRunDiff: document.getElementById('btn-run-diff'),
    diffResultsContainer: document.getElementById('diff-results-container'),

    // Toast
    toastContainer: document.getElementById('toast-container')
  };

  /* =========================================================================
     1. Initialization & Data Loading
     ========================================================================= */
  async function init() {
    setupThemeToggle();
    setupNavigation();
    setupFilters();
    setupUpdateTriggers();
    setupDiffComparator();

    // 1. Fast Load Insights for immediate KPIs & Charts
    await loadInsights();

    // 2. Load Full Changelog in background
    loadChangelog();
  }

  async function loadInsights() {
    try {
      // Chemin RELATIF, seule source : fonctionne en local (server.py sert /data/) comme
      // sur GitHub Pages (site servi sous /<dépôt>/). Un fetch ne rejette pas sur un 404 :
      // l'ancienne chaîne de .catch() ne se rabattait donc jamais.
      const res = await fetch('data/insights.json', { cache: 'no-cache' });

      if (!res.ok) throw new Error('Impossible de charger insights.json');
      state.insights = await res.json();
      
      renderKPIs(state.insights.metadata);
      renderAnalyseIA(state.insights.metadata?.analyseIA);
      renderPillars(state.insights.strategicPillars);
      renderGameChangers(state.insights.gameChangers);
      renderCharts(state.insights);
    } catch (err) {
      console.error('Chargement de insights.json impossible :', err);
      showToast('Données indisponibles : le tableau de bord ne peut pas s\'afficher.', 'error');
      elements.syncStatusText.textContent = 'Données indisponibles';
    }
  }

  async function loadChangelog() {
    try {
      const res = await fetch('data/changelog.json', { cache: 'no-cache' });

      if (!res.ok) throw new Error('Impossible de charger changelog.json');
      const data = await res.json();
      state.changelog = data.versions;

      populateDiffDropdowns(state.changelog);
      renderVersionExplorer();
    } catch (err) {
      console.error('Error loading changelog:', err);
      showToast('Erreur de chargement du changelog complet', 'error');
    }
  }

  /* =========================================================================
     2. KPI & Header Rendering
     ========================================================================= */
  function renderKPIs(meta) {
    if (!meta) return;
    // Une donnée absente s'affiche « — », jamais une valeur plausible écrite en dur :
    // un site figé ne doit pas avoir l'air à jour.
    elements.kpiTotalVersions.textContent = meta.totalVersions?.toLocaleString('fr-FR') ?? '—';
    elements.kpiTotalItems.textContent = meta.totalItems?.toLocaleString('fr-FR') ?? '—';
    elements.kpiLatestVer.textContent = meta.latestVersion ? 'v' + meta.latestVersion : '—';
    elements.kpiLatestDate.textContent = meta.latestDate || '—';
    elements.kpiHighImpact.textContent = meta.highImpactCount ?? '—';
    elements.headerVersionTag.textContent = meta.latestVersion ? 'v' + meta.latestVersion : '—';

    const quand = meta.lastUpdatedUtc
      ? new Date(meta.lastUpdatedUtc).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
      : (meta.lastUpdated || '').split(' ')[0];
    if (quand) {
      elements.syncStatusText.textContent = `Mis à jour le ${quand}`;
    }
  }

  /* =========================================================================
     3. Strategic Pillars (Comprendre le Potentiel)
     ========================================================================= */
  function renderPillars(pillars) {
    if (!pillars || !elements.pillarsContainer) return;

    elements.pillarsContainer.innerHTML = pillars.map(p => `
      <div class="pillar-card">
        <div class="pillar-top">
          <div class="pillar-icon-box">${p.icon}</div>
          <span class="pillar-badge">${p.badge}</span>
        </div>
        <h3 class="pillar-title">${escapeHTML(p.title)}</h3>
        <p class="pillar-summary">${escapeHTML(p.summary)}</p>
        <div class="pillar-metric">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          <span>${escapeHTML(p.metric)}</span>
        </div>
        ${p.keywords && p.keywords.length > 0 ? `
          <div style="margin-bottom: 0.85rem; font-size: 0.72rem; color: var(--text-muted); line-height: 1.4;">
            <span style="font-weight: 600;">Mots-clés filtrés :</span>
            <code style="font-size: 0.7rem; color: var(--brand-primary);">${escapeHTML(p.keywords.join(', '))}</code>
          </div>
        ` : ''}
        <ul class="pillar-list">
          ${p.details.map(d => `<li>${escapeHTML(d)}</li>`).join('')}
        </ul>
      </div>
    `).join('');
  }

  /* =========================================================================
     4. Game-Changers (Hall of Fame)
     ========================================================================= */
  function renderGameChangers(items) {
    if (!items || !elements.gamechangersContainer) return;

    elements.gamechangersContainer.innerHTML = items.map(item => `
      <div class="gamechanger-card">
        <div class="gamechanger-meta">
          <span class="version-pill">v${escapeHTML(item.version)}</span>
          <span class="date-text">${escapeHTML(item.date)}${item.sourceLine ? ` · Source : ligne ${item.sourceLine}` : ''}</span>
        </div>
        <h3 class="gamechanger-title">${escapeHTML(item.title)}</h3>
        <p class="gamechanger-desc">${escapeHTML(item.potential)}</p>
        <div class="gamechanger-quote">
          <code>"${escapeHTML(item.quote)}"</code>
        </div>
      </div>
    `).join('');
  }

  /* =========================================================================
     5. Interactive Charts (Chart.js)
     ========================================================================= */
  function renderCharts(insights) {
    if (typeof Chart === 'undefined') {
      console.warn('Chart.js not yet loaded');
      return;
    }

    const isDark = state.theme === 'dark';
    const textColor = isDark ? '#a1a1aa' : '#64748b';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)';

    // Chart 1: Monthly Timeline
    const timelineCtx = document.getElementById('chart-timeline')?.getContext('2d');
    if (timelineCtx && insights.timeline) {
      if (state.charts.timeline) state.charts.timeline.destroy();

      const labels = insights.timeline.map(d => d.month);
      const releasesData = insights.timeline.map(d => d.releases);
      const itemsData = insights.timeline.map(d => d.items);

      state.charts.timeline = new Chart(timelineCtx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              type: 'line',
              label: 'Modifications / Mois',
              data: itemsData,
              borderColor: '#ea580c',
              backgroundColor: 'rgba(234, 88, 12, 0.1)',
              borderWidth: 2,
              pointRadius: 3,
              pointHoverRadius: 6,
              yAxisID: 'y1',
              tension: 0.35,
              fill: true
            },
            {
              type: 'bar',
              label: 'Nombre de Releases',
              data: releasesData,
              backgroundColor: isDark ? 'rgba(217, 119, 6, 0.65)' : 'rgba(217, 119, 6, 0.85)',
              borderRadius: 4,
              yAxisID: 'y'
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              labels: { color: textColor, font: { family: 'Inter', size: 11 } }
            },
            tooltip: {
              backgroundColor: isDark ? '#18181f' : '#ffffff',
              titleColor: isDark ? '#f4f4f5' : '#0f172a',
              bodyColor: isDark ? '#a1a1aa' : '#475569',
              borderColor: isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0',
              borderWidth: 1,
              padding: 10
            }
          },
          scales: {
            x: {
              grid: { color: gridColor },
              ticks: { color: textColor, font: { family: 'Inter', size: 10 } }
            },
            y: {
              position: 'left',
              title: { display: true, text: 'Releases / mois', color: textColor, font: { size: 10 } },
              grid: { color: gridColor },
              ticks: { color: textColor, font: { size: 10 } }
            },
            y1: {
              position: 'right',
              title: { display: true, text: 'Modifications', color: textColor, font: { size: 10 } },
              grid: { drawOnChartArea: false },
              ticks: { color: textColor, font: { size: 10 } }
            }
          }
        }
      });
    }

    // Chart 2: Category Breakdown (Doughnut)
    const catCtx = document.getElementById('chart-categories')?.getContext('2d');
    if (catCtx && insights.actionCounts) {
      if (state.charts.categories) state.charts.categories.destroy();

      const acts = insights.actionCounts;
      state.charts.categories = new Chart(catCtx, {
        type: 'doughnut',
        data: {
          labels: ['Fixes (Correctifs)', 'Ajouts (Features)', 'Améliorations (UX/Perf)', 'Changements', 'Suppressions'],
          datasets: [{
            data: [acts.Fixed || 0, acts.Added || 0, acts.Improved || 0, acts.Changed || 0, acts.Removed || 0],
            backgroundColor: ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444'],
            borderWidth: 0,
            hoverOffset: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom',
              labels: { color: textColor, boxWidth: 12, font: { family: 'Inter', size: 11 } }
            }
          },
          cutout: '68%'
        }
      });
    }

    // Chart 3: Strategic Tags Distribution
    const tagsCtx = document.getElementById('chart-tags')?.getContext('2d');
    if (tagsCtx && insights.tagCounts) {
      if (state.charts.tags) state.charts.tags.destroy();

      const tags = Object.entries(insights.tagCounts)
        .filter(([k]) => k !== 'General Core')
        .sort((a, b) => b[1] - a[1]);

      state.charts.tags = new Chart(tagsCtx, {
        type: 'bar',
        data: {
          labels: tags.map(t => t[0]),
          datasets: [{
            label: 'Modifications',
            data: tags.map(t => t[1]),
            backgroundColor: [
              '#8b5cf6', '#06b6d4', '#f43f5e', '#d97706', '#3b82f6', '#10b981', '#ec4899'
            ],
            borderRadius: 6
          }]
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false }
          },
          scales: {
            x: {
              grid: { color: gridColor },
              ticks: { color: textColor, font: { size: 10 } }
            },
            y: {
              grid: { display: false },
              ticks: { color: textColor, font: { family: 'Inter', size: 11, weight: '500' } }
            }
          }
        }
      });
    }
  }

  /* =========================================================================
     6. Version Explorer & Filtering
     ========================================================================= */
  function renderVersionExplorer() {
    if (!state.changelog || !elements.versionsContainer) return;

    // Filter versions
    const query = state.searchQuery.trim().toLowerCase();
    const tag = state.selectedTag;
    const action = state.selectedAction;

    let filtered = [];

    for (const v of state.changelog) {
      const matchingItems = v.items.filter(item => {
        // Tag filter
        if (tag !== 'all' && !item.tags.includes(tag)) {
          return false;
        }
        // Action filter
        if (action !== 'all' && item.actionType !== action) {
          return false;
        }
        // Search query filter
        if (query) {
          const matchText = item.text.toLowerCase().includes(query);
          const matchScope = item.scope.toLowerCase().includes(query);
          const matchVer = v.version.toLowerCase().includes(query);
          return matchText || matchScope || matchVer;
        }
        return true;
      });

      if (matchingItems.length > 0) {
        filtered.push({
          ...v,
          matchingItems
        });
      }
    }

    elements.resultsCountText.textContent = `${filtered.length} versions correspondent à vos filtres (${filtered.reduce((acc, v) => acc + v.matchingItems.length, 0)} modifications)`;

    // Slice for performance
    const toDisplay = filtered.slice(0, state.visibleVersionLimit);

    elements.versionsContainer.innerHTML = toDisplay.map((v, idx) => {
      // First version is open by default
      const isOpen = idx === 0 || query.length > 0;
      
      const addedCount = v.matchingItems.filter(i => i.actionType === 'Added').length;
      const fixedCount = v.matchingItems.filter(i => i.actionType === 'Fixed').length;
      const improvedCount = v.matchingItems.filter(i => i.actionType === 'Improved').length;

      return `
        <article class="version-card ${isOpen ? 'open' : ''}" data-version="${escapeHTML(v.version)}">
          <div class="version-header" role="button" tabindex="0">
            <div class="version-title-group">
              <span class="version-badge">v${escapeHTML(v.version)}</span>
              <span class="version-date">${escapeHTML(v.date)}</span>
            </div>

            <div class="version-counts">
              ${addedCount > 0 ? `<span class="pill-count added">+${addedCount}</span>` : ''}
              ${fixedCount > 0 ? `<span class="pill-count fixed">fix ${fixedCount}</span>` : ''}
              ${improvedCount > 0 ? `<span class="pill-count improved">imp ${improvedCount}</span>` : ''}
              <span class="toggle-arrow">▼</span>
            </div>
          </div>

          <div class="version-body">
            ${v.matchingItems.map(item => `
              <div class="change-item">
                <span class="action-badge ${item.actionType}">${item.actionType}</span>
                <div class="change-content">
                  ${item.scope !== 'Core CLI' ? `<span class="change-scope">[${escapeHTML(item.scope)}]</span>` : ''}
                  <span>${formatChangeText(item.cleanText, query)}</span>
                  ${item.impact === 'High' && !item.ia ? `<span class="impact-star" title="Innovation de rupture">★ High Impact</span>` : ''}
                  ${item.ia ? `<div class="ia-analyse" title="Analyse locale par un modèle de langage">
                    <span class="ia-impact ia-${escapeHTML(item.ia.impact)}">${escapeHTML(item.ia.impact)}</span>
                    <span class="mini-tag">${escapeHTML(item.ia.domaine)}</span>
                    <span class="ia-resume">${escapeHTML(item.ia.resume)}</span>
                  </div>` : ''}
                  <div class="change-tags">
                    ${item.tags.map(t => `<span class="mini-tag">${escapeHTML(t)}</span>`).join('')}
                  </div>
                </div>
              </div>
            `).join('')}
          </div>
        </article>
      `;
    }).join('');

    // Toggle card on header click
    document.querySelectorAll('.version-header').forEach(header => {
      header.addEventListener('click', () => {
        const card = header.closest('.version-card');
        card.classList.toggle('open');
      });
      header.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          header.click();
        }
      });
    });

    // Handle Load More button
    if (filtered.length > state.visibleVersionLimit) {
      elements.loadMoreContainer.style.display = 'flex';
      elements.btnLoadMore.onclick = () => {
        state.visibleVersionLimit += 25;
        renderVersionExplorer();
      };
    } else {
      elements.loadMoreContainer.style.display = 'none';
    }
  }

  function formatChangeText(text, query) {
    let escaped = escapeHTML(text);

    // Format backticks into <code>
    escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Highlight search query
    if (query) {
      const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
      escaped = escaped.replace(regex, '<mark style="background: rgba(245, 158, 11, 0.4); color: inherit; padding: 0.1rem 0.2rem; border-radius: 3px;">$1</mark>');
    }

    return escaped;
  }

  function setupFilters() {
    // Search input with debounce
    let debounceTimer;
    elements.searchInput?.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        state.searchQuery = e.target.value;
        state.visibleVersionLimit = 25;
        renderVersionExplorer();
      }, 200);
    });

    elements.btnClearSearch?.addEventListener('click', () => {
      elements.searchInput.value = '';
      state.searchQuery = '';
      state.selectedTag = 'all';
      state.selectedAction = 'all';
      elements.tagChips.forEach(c => c.classList.toggle('active', c.dataset.filterTag === 'all'));
      elements.actionChips.forEach(c => c.classList.toggle('active', c.dataset.filterAction === 'all'));
      state.visibleVersionLimit = 25;
      renderVersionExplorer();
    });

    // Tag Filter chips
    elements.tagChips.forEach(chip => {
      chip.addEventListener('click', () => {
        elements.tagChips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.selectedTag = chip.dataset.filterTag;
        state.visibleVersionLimit = 25;
        renderVersionExplorer();
      });
    });

    // Action Filter chips
    elements.actionChips.forEach(chip => {
      chip.addEventListener('click', () => {
        elements.actionChips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.selectedAction = chip.dataset.filterAction;
        state.visibleVersionLimit = 25;
        renderVersionExplorer();
      });
    });

    // Toggle all cards
    elements.btnToggleAllCards?.addEventListener('click', () => {
      const cards = document.querySelectorAll('.version-card');
      const allOpen = Array.from(cards).every(c => c.classList.contains('open'));
      cards.forEach(c => c.classList.toggle('open', !allOpen));
    });
  }

  /* =========================================================================
     7. Version Comparator (Diff Tool)
     ========================================================================= */
  function populateDiffDropdowns(versions) {
    if (!versions || !elements.selectVersionA || !elements.selectVersionB) return;

    const options = versions.map((v, i) => `
      <option value="${escapeHTML(v.version)}" ${i === 1 ? 'selected' : ''}>
        v${escapeHTML(v.version)} (${escapeHTML(v.date)})
      </option>
    `).join('');

    elements.selectVersionA.innerHTML = options;
    elements.selectVersionB.innerHTML = versions.map((v, i) => `
      <option value="${escapeHTML(v.version)}" ${i === 0 ? 'selected' : ''}>
        v${escapeHTML(v.version)} (${escapeHTML(v.date)})
      </option>
    `).join('');
  }

  function setupDiffComparator() {
    elements.btnRunDiff?.addEventListener('click', () => {
      const verA = elements.selectVersionA.value;
      const verB = elements.selectVersionB.value;

      if (!state.changelog) return;
      if (verA === verB) {
        elements.diffResultsContainer.innerHTML = `
          <div class="stat-card" style="text-align: center; padding: 2rem;">
            <p>Veuillez choisir deux versions différentes pour visualiser les changements.</p>
          </div>
        `;
        return;
      }

      // Find indices in changelog (versions are sorted newest first)
      const idxA = state.changelog.findIndex(v => v.version === verA);
      const idxB = state.changelog.findIndex(v => v.version === verB);

      if (idxA === -1 || idxB === -1) return;

      const olderIdx = Math.max(idxA, idxB);
      const newerIdx = Math.min(idxA, idxB);

      const olderVer = state.changelog[olderIdx];
      const newerVer = state.changelog[newerIdx];

      // Collect all versions between older and newer
      const intermediateVersions = state.changelog.slice(newerIdx, olderIdx);
      const intermediateItems = intermediateVersions.flatMap(v => v.items);

      const added = intermediateItems.filter(i => i.actionType === 'Added');
      const fixed = intermediateItems.filter(i => i.actionType === 'Fixed');
      const improved = intermediateItems.filter(i => i.actionType === 'Improved');
      const others = intermediateItems.filter(i => !['Added', 'Fixed', 'Improved'].includes(i.actionType));

      elements.diffResultsContainer.innerHTML = `
        <div class="stat-card" style="margin-bottom: 1.5rem; background: var(--bg-surface);">
          <h3 style="font-family: var(--font-heading); font-size: 1.15rem; margin-bottom: 0.5rem;">
            Différence entre v${escapeHTML(olderVer.version)} et v${escapeHTML(newerVer.version)}
          </h3>
          <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
            <strong>${intermediateVersions.length}</strong> versions publiées dans cet intervalle, comprenant <strong>${intermediateItems.length}</strong> modifications cumulées.
          </p>
          <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
            <span class="pill-count added">+${added.length} Nouveautés</span>
            <span class="pill-count fixed">🛠️ ${fixed.length} Correctifs</span>
            <span class="pill-count improved">⚡ ${improved.length} Améliorations</span>
          </div>
        </div>

        ${added.length > 0 ? `
          <div class="stat-card" style="margin-bottom: 1.25rem;">
            <h4 style="color: var(--cat-added); font-weight: 700; margin-bottom: 0.75rem;">✨ Nouvelles Fonctionnalités Déployées (${added.length})</h4>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
              ${added.map(item => `
                <div style="font-size: 0.85rem; padding: 0.4rem 0; border-bottom: 1px solid var(--border-subtle);">
                  <span class="version-pill" style="font-size: 0.65rem; padding: 0.1rem 0.4rem; margin-right: 0.4rem;">v${item.version}</span>
                  ${escapeHTML(item.cleanText)}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        ${improved.length > 0 ? `
          <div class="stat-card" style="margin-bottom: 1.25rem;">
            <h4 style="color: var(--cat-improved); font-weight: 700; margin-bottom: 0.75rem;">⚡ Améliorations & Optimisations (${improved.length})</h4>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
              ${improved.slice(0, 50).map(item => `
                <div style="font-size: 0.85rem; padding: 0.4rem 0; border-bottom: 1px solid var(--border-subtle);">
                  <span class="version-pill" style="font-size: 0.65rem; padding: 0.1rem 0.4rem; margin-right: 0.4rem;">v${item.version}</span>
                  ${escapeHTML(item.cleanText)}
                </div>
              `).join('')}
              ${improved.length > 50 ? `<div style="font-size: 0.8rem; color: var(--text-dim); text-align: center;">... et ${improved.length - 50} autres améliorations</div>` : ''}
            </div>
          </div>
        ` : ''}

        ${fixed.length > 0 ? `
          <div class="stat-card">
            <h4 style="color: var(--cat-fixed); font-weight: 700; margin-bottom: 0.75rem;">🛠️ Correctifs & Résilience (${fixed.length})</h4>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
              ${fixed.slice(0, 50).map(item => `
                <div style="font-size: 0.85rem; padding: 0.4rem 0; border-bottom: 1px solid var(--border-subtle);">
                  <span class="version-pill" style="font-size: 0.65rem; padding: 0.1rem 0.4rem; margin-right: 0.4rem;">v${item.version}</span>
                  ${escapeHTML(item.cleanText)}
                </div>
              `).join('')}
              ${fixed.length > 50 ? `<div style="font-size: 0.8rem; color: var(--text-dim); text-align: center;">... et ${fixed.length - 50} autres correctifs</div>` : ''}
            </div>
          </div>
        ` : ''}
      `;
    });
  }

  /* =========================================================================
     8. Live Updates Trigger
     ========================================================================= */
  const EST_LOCAL = ['localhost', '127.0.0.1'].includes(location.hostname);

  function setupUpdateTriggers() {
    async function triggerUpdate() {
      elements.updateBtnLabel.textContent = 'Synchronisation...';
      elements.btnTriggerUpdate.disabled = true;
      if (elements.btnManualSync) elements.btnManualSync.disabled = true;
      showToast('Téléchargement du changelog officiel en cours...', 'info');

      try {
        const res = await fetch('/api/update', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
          showToast(`Changelog synchronisé : v${data.metadata.latestVersion} (${data.metadata.totalVersions} versions)`, 'success');
          if (elements.manualSyncFeedback) {
            elements.manualSyncFeedback.textContent = `Succès à ${new Date().toLocaleTimeString()} : ${data.metadata.totalVersions} versions indexées.`;
          }
          await loadInsights();
          await loadChangelog();
        } else {
          throw new Error(data.error || 'Erreur inconnue');
        }
      } catch (err) {
        console.error('Update error:', err);
        showToast('Échec de la mise à jour : ' + err.message, 'error');
        if (elements.manualSyncFeedback) {
          elements.manualSyncFeedback.textContent = 'Erreur lors de la dernière tentative. Vérifiez les logs.';
        }
      } finally {
        elements.updateBtnLabel.textContent = 'Mettre à jour';
        elements.btnTriggerUpdate.disabled = false;
        if (elements.btnManualSync) elements.btnManualSync.disabled = false;
      }
    }

    if (!EST_LOCAL) {
      // En ligne (GitHub Pages) : pas d'API, la mise à jour est faite chaque jour par
      // GitHub Actions. Bouton et onglet d'automatisation locale retirés.
      elements.btnTriggerUpdate?.remove();
      document.getElementById('btn-tab-automation')?.remove();
      document.getElementById('tab-automation')?.remove();
      return;
    }
    elements.btnTriggerUpdate?.addEventListener('click', triggerUpdate);
    elements.btnManualSync?.addEventListener('click', triggerUpdate);
  }

  /* =========================================================================
     9. Navigation & Tabs
     ========================================================================= */
  function setupNavigation() {
    elements.tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const targetId = tab.dataset.tab;
        elements.tabs.forEach(t => t.classList.remove('active'));
        elements.sections.forEach(s => s.classList.remove('active'));

        tab.classList.add('active');
        const targetSection = document.getElementById(targetId);
        if (targetSection) {
          targetSection.classList.add('active');
          state.activeTab = targetId;
        }

        // Re-render charts when overview becomes visible
        if (targetId === 'tab-overview' && state.insights) {
          setTimeout(() => renderCharts(state.insights), 50);
        }
      });
    });
  }

  /* =========================================================================
     10. Theme Toggle
     ========================================================================= */
  function setupThemeToggle() {
    elements.themeToggle?.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('claude-obs-theme', next);
      state.theme = next;

      // Update Chart Colors
      if (state.insights) {
        renderCharts(state.insights);
      }
    });
  }

  /* =========================================================================
     11. Toast Notifications & Helpers
     ========================================================================= */
  function showToast(message, type = 'info') {
    if (!elements.toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
      <span>${escapeHTML(message)}</span>
    `;

    elements.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // Pied de page : ce qui a été analysé par le modèle local, et ce qui attend encore.
  // Construit sans innerHTML (texte venu des données).
  function renderAnalyseIA(ia) {
    const cible = document.getElementById('analyse-ia-statut');
    if (!cible) return;
    if (!ia) {
      cible.textContent = 'Classement par mots-clés uniquement.';
      return;
    }
    const n = ia.versionsAnalysees?.length || 0;
    let texte = n
      ? `Analyse locale par un modèle de langage des ${n} version(s) parue(s) depuis la mise en service : ${ia.entreesAnalysees} entrée(s) résumée(s) en français. Versions antérieures : classement par mots-clés.`
      : `Analyse locale par un modèle de langage, active pour les prochaines versions ; l'historique est classé par mots-clés.`;
    if (n) texte += ' Résumés générés automatiquement : ils peuvent simplifier ou généraliser, le texte officiel affiché au-dessus fait foi.';
    if (ia.enAttente > 0) texte += ` ⚠ ${ia.enAttente} entrée(s) en attente d'analyse.`;
    cible.textContent = texte;
  }

  function escapeHTML(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Start app when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
