import React, { useState, useEffect, useRef, useCallback } from 'react';

const LIMIT_OPTIONS = [5, 7, 10, 15];

const DEFAULT_FILTERS = {
    minDistance: '',
    maxDistance: '',
    minElevation: '',
    maxElevation: '',
    tags: [],
    limit: 7,
};

export default function NearbyFilterModal({ isOpen, onClose, onApply, currentFilters }) {
    const [filters, setFilters] = useState({ ...DEFAULT_FILTERS, ...currentFilters });
    const [allTags, setAllTags] = useState([]);
    const [tagQuery, setTagQuery] = useState('');
    const [showTagDropdown, setShowTagDropdown] = useState(false);
    const tagInputRef = useRef(null);
    const dropdownRef = useRef(null);

    useEffect(() => {
        if (isOpen) {
            setFilters({ ...DEFAULT_FILTERS, ...currentFilters });
            fetch('/api/routes/tags')
                .then(res => res.ok ? res.json() : [])
                .then(setAllTags)
                .catch(() => setAllTags([]));
        }
    }, [isOpen, currentFilters]);

    // Close dropdown on outside click
    useEffect(() => {
        const handleClick = (e) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target) &&
                tagInputRef.current && !tagInputRef.current.contains(e.target)) {
                setShowTagDropdown(false);
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, []);

    const filteredTags = allTags.filter(t =>
        !filters.tags.includes(t.slug) &&
        (tagQuery === '' || t.name.includes(tagQuery) || t.slug.includes(tagQuery))
    );

    const addTag = useCallback((slug) => {
        setFilters(f => ({ ...f, tags: [...f.tags, slug] }));
        setTagQuery('');
        setShowTagDropdown(false);
    }, []);

    const removeTag = useCallback((slug) => {
        setFilters(f => ({ ...f, tags: f.tags.filter(t => t !== slug) }));
    }, []);

    const handleApply = () => {
        onApply(filters);
        onClose();
    };

    const handleReset = () => {
        const reset = { ...DEFAULT_FILTERS };
        setFilters(reset);
        onApply(reset);
        onClose();
    };

    const hasActiveFilters = filters.minDistance !== '' || filters.maxDistance !== '' ||
        filters.minElevation !== '' || filters.maxElevation !== '' ||
        filters.tags.length > 0 || filters.limit !== 7;

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
            <div
                className="relative w-full max-w-sm bg-gray-900/95 border border-gray-700 rounded-2xl shadow-2xl backdrop-blur-md overflow-hidden"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700/50">
                    <h3 className="text-base font-bold text-white">탐색 필터</h3>
                    <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Body */}
                <div className="px-5 py-4 space-y-5 max-h-[65vh] overflow-y-auto">
                    {/* Distance */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">거리 (km)</label>
                        <div className="flex items-center gap-2 mt-1.5">
                            <input
                                type="number"
                                placeholder="최소"
                                value={filters.minDistance}
                                onChange={e => setFilters(f => ({ ...f, minDistance: e.target.value }))}
                                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                            />
                            <span className="text-gray-500 text-sm">~</span>
                            <input
                                type="number"
                                placeholder="최대"
                                value={filters.maxDistance}
                                onChange={e => setFilters(f => ({ ...f, maxDistance: e.target.value }))}
                                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                            />
                        </div>
                    </div>

                    {/* Elevation */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">획득고도 (m)</label>
                        <div className="flex items-center gap-2 mt-1.5">
                            <input
                                type="number"
                                placeholder="최소"
                                value={filters.minElevation}
                                onChange={e => setFilters(f => ({ ...f, minElevation: e.target.value }))}
                                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                            />
                            <span className="text-gray-500 text-sm">~</span>
                            <input
                                type="number"
                                placeholder="최대"
                                value={filters.maxElevation}
                                onChange={e => setFilters(f => ({ ...f, maxElevation: e.target.value }))}
                                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                            />
                        </div>
                    </div>

                    {/* Tags */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">태그</label>
                        {/* Selected tags */}
                        {filters.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-1.5 mb-2">
                                {filters.tags.map(slug => (
                                    <span key={slug} className="inline-flex items-center gap-1 bg-blue-500/20 border border-blue-400/30 text-blue-300 text-xs px-2.5 py-1 rounded-full">
                                        {allTags.find(t => t.slug === slug)?.name || slug}
                                        <button onClick={() => removeTag(slug)} className="hover:text-white">
                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                            </svg>
                                        </button>
                                    </span>
                                ))}
                            </div>
                        )}
                        {/* Tag search input */}
                        <div className="relative mt-1.5">
                            <input
                                ref={tagInputRef}
                                type="text"
                                placeholder="태그 검색..."
                                value={tagQuery}
                                onChange={e => { setTagQuery(e.target.value); setShowTagDropdown(true); }}
                                onFocus={() => setShowTagDropdown(true)}
                                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                            />
                            {showTagDropdown && filteredTags.length > 0 && (
                                <div ref={dropdownRef} className="absolute left-0 right-0 mt-1 max-h-36 overflow-y-auto bg-gray-800 border border-gray-600 rounded-lg shadow-xl z-10">
                                    {filteredTags.map(tag => (
                                        <button
                                            key={tag.slug}
                                            onClick={() => addTag(tag.slug)}
                                            className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white flex justify-between items-center"
                                        >
                                            <span>{tag.name}</span>
                                            <span className="text-[10px] text-gray-500">{tag.count}</span>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Limit */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">결과 수</label>
                        <select
                            value={filters.limit}
                            onChange={e => setFilters(f => ({ ...f, limit: parseInt(e.target.value) }))}
                            className="w-full mt-1.5 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                        >
                            {LIMIT_OPTIONS.map(n => (
                                <option key={n} value={n}>{n}개</option>
                            ))}
                        </select>
                    </div>

                    {/* Verified only */}
                    <div className="flex items-center justify-between opacity-50">
                        <div>
                            <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">검증 코스만 보기</label>
                            <p className="text-[10px] text-gray-500 mt-0.5">준비 중인 기능입니다</p>
                        </div>
                        <input
                            type="checkbox"
                            disabled
                            className="w-4 h-4 rounded border-gray-600 bg-gray-800 cursor-not-allowed"
                        />
                    </div>
                </div>

                {/* Footer */}
                <div className="flex gap-2 px-5 py-4 border-t border-gray-700/50">
                    <button
                        onClick={handleReset}
                        disabled={!hasActiveFilters}
                        className="flex-1 px-4 py-2.5 text-sm font-medium rounded-xl border border-gray-600 text-gray-300 hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                        초기화
                    </button>
                    <button
                        onClick={handleApply}
                        className="flex-1 px-4 py-2.5 text-sm font-bold rounded-xl bg-blue-600 text-white hover:bg-blue-500 transition-colors"
                    >
                        적용
                    </button>
                </div>
            </div>
        </div>
    );
}

export { DEFAULT_FILTERS };
