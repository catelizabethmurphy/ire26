// ── HAMBURGER / MOBILE MENU ──────────────────────────────
const hamburger  = document.querySelector('.hamburger');
const mobileMenu = document.querySelector('.mobile-menu');
if (hamburger && mobileMenu) {
  hamburger.addEventListener('click', () => {
    hamburger.classList.toggle('active');
    mobileMenu.classList.toggle('active');
  });
  // close menu when a link is tapped
  mobileMenu.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      hamburger.classList.remove('active');
      mobileMenu.classList.remove('active');
    });
  });
}

// ── SCROLLYTELLING TORNADO ───────────────────────────────
const rounds = ['first-four','first-round','second-round','sweet-16','elite-eight','final-four','national-championship'];

const svg          = d3.select('#tornado-container svg');
const paths        = svg.selectAll('path');
const steps        = d3.selectAll('.step');
const stepContents = d3.selectAll('.step-content');
const roundLabels  = d3.selectAll('.round-label');

const fullWidth  = 2707.77;
const fullHeight = 6281.84;
const padding    = 50;

const roundExtents = {};
rounds.forEach(id => {
  const el = document.getElementById(id);
  if (el) { const bbox = el.getBBox(); roundExtents[id] = fullHeight - bbox.y; }
});

paths.style('opacity', 0).style('stroke-width', 0);
roundLabels.style('opacity', 0);

const initialHeight = (roundExtents['first-four'] || fullHeight) + padding;
svg.attr('viewBox', `0 ${fullHeight - initialHeight} ${fullWidth} ${initialHeight}`);

function handleStepEnter(round) {
  if (!rounds.includes(round)) return;

  const currentIndex  = rounds.indexOf(round);
  const viewBoxHeight = (roundExtents[round] || fullHeight) + padding;
  const viewBoxY      = fullHeight - viewBoxHeight;

  svg.transition().duration(500).ease(d3.easeCubicInOut)
     .attr('viewBox', `0 ${viewBoxY} ${fullWidth} ${viewBoxHeight}`);

  paths.each(function() {
    const id = this.id;
    const pathIndex = rounds.indexOf(id);
    d3.select(this).style('opacity', pathIndex <= currentIndex ? 1 : 0);
  });
  roundLabels.each(function() {
    const id = this.dataset.round;
    const labelIndex = rounds.indexOf(id);
    d3.select(this).style('opacity', labelIndex <= currentIndex ? 1 : 0);
  });

  steps.classed('is-active', false);
  roundLabels.classed('is-active', false);
  d3.select(`.step[data-round="${round}"]`).classed('is-active', true);
  d3.select(`.round-label[data-round="${round}"]`).classed('is-active', true);
}

const observer = new IntersectionObserver(
  entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const round = entry.target.parentElement.dataset.round;
        handleStepEnter(round);
      }
    });
  },
  { rootMargin: '-80% 0px -20% 0px', threshold: 0 }
);

stepContents.each(function() { observer.observe(this); });
handleStepEnter('first-four');
