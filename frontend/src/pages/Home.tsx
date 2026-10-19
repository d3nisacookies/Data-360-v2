import { Link } from 'react-router-dom'
import { useAuth } from '../auth'
import { lastClient, useBorrowers } from '../components/Shell'

export default function Home() {
  const { canEdit } = useAuth()
  const q = useBorrowers()
  const n = q.data?.length ?? 0
  const first = lastClient() ?? q.data?.[0]?.id
  return (
    <div>
      <header className="top"><div className="brand"><b>Data360</b><span>Trusted data for credit decisions</span></div>
        <span className="hright">{canEdit && <Link to="/upload" className="btn">Upload files</Link>}<Link to="/console" className="btn primary">Open the console</Link></span></header>

      <section className="hhero">
        <div className="hcopy">
          <span className="heyebrow">For credit, risk and data teams at banks</span>
          <h1>Know whether you can trust the data behind every credit decision.</h1>
          <p className="hlead">Data360 finds a corporate client's loan information across your systems and outside sources, checks how reliable it is,
            fixes what it can, and produces a credit memo where every number shows where it came from.</p>
          <div className="hcta">
            {n ? <Link className="btn primary big" to={first ? `/b/${first}/p1/source` : '/console'}>Start with Phase 1</Link>
              : canEdit ? <Link className="btn primary big" to="/upload">Upload your first files</Link> : <Link className="btn primary big" to="/console">Open the console</Link>}
          </div>
          <p className="hint">{n ? `${n} borrower${n > 1 ? 's' : ''} found in your uploaded files.` : 'Upload data-dictionary exports and vendor files (Excel or CSV) to begin.'}</p>
        </div>
        <div className="hvisual" aria-label="What Data360 does">
          <div className="hv-step"><span className="hv-n">1</span><div><b>Every source searched</b><span>Internal systems and outside feeds, from the files you upload</span></div></div>
          <div className="hv-step"><span className="hv-n">2</span><div><b>Confidence score</b><span>Seven checks, before and after cleaning</span><div className="hv-bar"><i style={{ width: '70%' }} /><em style={{ left: '70%', width: '12%' }} /></div></div></div>
          <div className="hv-step"><span className="hv-n">3</span><div><b>Credit memo with sources</b><span>Policy checks give a draft decision for approvers</span></div></div>
          <div className="hv-step"><span className="hv-n">4</span><div><b>A fix plan by file</b><span>Who fixes what, and by when</span></div></div>
          <div className="hv-cap">Illustration · your figures appear in the console</div>
        </div>
      </section>

      <section className="hsec"><h2>The problem it solves</h2>
        <div className="hcards">
          <div className="hcard"><span className="hic" aria-hidden="true">⌕</span><b>The data is scattered</b><p>A single credit memo pulls data from loan systems, risk platforms, CRM, legal files, market feeds and paper records. Analysts spend days chasing it.</p></div>
          <div className="hcard"><span className="hic" aria-hidden="true">≠</span><b>The numbers disagree</b><p>The loan system says one facility amount, the market feed says another. Nobody is sure which one is right, or who should fix it.</p></div>
          <div className="hcard"><span className="hic" aria-hidden="true">?</span><b>Nobody can prove where a number came from</b><p>When a reviewer or regulator asks "where did this figure come from?", the answer is usually a spreadsheet and a guess.</p></div>
        </div></section>

      <section className="hsec"><h2>How it works, in three phases</h2>
        <ol className="hphases">
          <li className="hp p1"><span className="hk">Phase 1</span><b>Assess &amp; improve</b><p>Find every piece of data about the borrower, score how trustworthy it is, clean it, agree common definitions, and build the credit memo.</p><span className="hout">You get: a confidence score, a cleaned data pack, a credit memo with sources</span></li>
          <li className="hp p2"><span className="hk">Phase 2</span><b>Improve &amp; plan</b><p>List what's missing or broken, recommend fixes in priority order, rate each data area, and build a costed roadmap.</p><span className="hout">You get: a gap list, recommendations, a roadmap and business case</span></li>
          <li className="hp p3"><span className="hk">Phase 3</span><b>Transform</b><p>Carry out the roadmap in four stages, from fixing the basics to AI-assisted memos and early warnings.</p><span className="hout">You get: project plans, certified data, alerts before problems happen</span></li>
        </ol>
        <p className="hint">Each phase unlocks when the one before it is signed off, the same way a bank's own approvals work.</p></section>

      <section className="hsec"><h2>Words you'll see</h2>
        <dl className="hgloss">
          <div><dt>Confidence score</dt><dd>How far the data can be trusted, from seven checks such as completeness, accuracy and timeliness.</dd></div>
          <div><dt>Golden record</dt><dd>The one agreed value for each field, taken from the most reliable source.</dd></div>
          <div><dt>Escalation</dt><dd>A problem Data360 can't fix on its own, sent to a named owner with a due date.</dd></div>
          <div><dt>Credit memo</dt><dd>The document a credit committee reads before approving a loan.</dd></div>
          <div><dt>Refer</dt><dd>The memo's draft decision when policy checks fail: it goes to the credit committee to decide.</dd></div>
          <div><dt>Rules &amp; policies</dt><dd>The regulations and bank policies the memo is checked against. Open them any time from the button at the bottom right.</dd></div>
        </dl></section>

      <section className="hfinal"><div><b>Ready to look?</b><span>Open the console to see each borrower's progress through the three phases.</span></div>
        <span className="hcta"><Link className="btn primary big" to="/console">Open the console</Link>{canEdit && <Link className="btn big" to="/upload">Upload files</Link>}</span></section>
      <p className="hfoot hint">Prepared data supports analysis; approvers make credit decisions.</p>
    </div>
  )
}
