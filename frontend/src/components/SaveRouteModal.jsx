import React, { useState, useEffect, useRef, useCallback } from 'react';
import apiClient from '../utils/apiClient';
import ReactMarkdown from 'react-markdown';

const SaveRouteModal = ({
    isOpen,
    onClose,
    onSave,
    initialData = {},
    isOwner = false,
    isLoading = false,
    isMapChanged = false,
    sectionsVersion = 0,
    autoTagPayload = null,
    onAutoTagsGenerated = () => {}
}) => {
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [status, setStatus] = useState('PUBLIC');
    const [tags, setTags] = useState([]);
    const [tagInput, setTagInput] = useState('');
    const [descPreview, setDescPreview] = useState(false);
    const [suggestions, setSuggestions] = useState([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [suggestionsLoading, setSuggestionsLoading] = useState(false);
    const [isAiGenerating, setIsAiGenerating] = useState(false);
    const [generatedAtVersion, setGeneratedAtVersion] = useState(-1);
    const debounceRef = useRef(null);
    const suggestionsRef = useRef(null);
    const inputRef = useRef(null);

    // Route changed since last AI generation?
    const routeChangedSinceGeneration = generatedAtVersion >= 0 && sectionsVersion > generatedAtVersion;

    useEffect(() => {
        if (isOpen) {
            setTitle(initialData.title || '');
            setDescription(initialData.description || '');
            setStatus(initialData.status || 'PUBLIC');
            setTags(initialData.tags || []);
            setTagInput('');
            setSuggestions([]);
            setShowSuggestions(false);

            // Set to preview mode by default
            setDescPreview(true);

            // Preload popular tags
            fetchSuggestions('');

            // Auto-generate only when description is empty (new route / GPX import)
            if (autoTagPayload && !initialData.description && generatedAtVersion < 0) {
                generateAutoTags(autoTagPayload);
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen]);

    // Reset when a different route is loaded
    const prevRouteIdRef = useRef(initialData.id);
    useEffect(() => {
        if (initialData.id !== prevRouteIdRef.current) {
            setGeneratedAtVersion(-1);
            prevRouteIdRef.current = initialData.id;
        }
    }, [initialData.id]);

    const generateAutoTags = async (payload) => {
        setIsAiGenerating(true);
        setDescPreview(false);
        setDescription('');

        try {
            const data = await apiClient.post('/api/routes/auto-tag', payload);
            if (data) {
                if (data.tags && data.tags.length > 0) {
                    setTags(prev => Array.from(new Set([...prev, ...data.tags])));
                }
                if (data.description) {
                    setDescription(data.description);
                    setDescPreview(true);
                }
                if (data.title && !title) {
                    setTitle(data.title);
                }
                onAutoTagsGenerated(data.description, data.tags, data.title);
                setGeneratedAtVersion(sectionsVersion);
            }
        } catch (err) {
            console.error('Auto tag generation failed:', err);
            if (!description) setDescription(initialData.description || '');
        } finally {
            setIsAiGenerating(false);
        }
    };

    // Close suggestions on outside click
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (suggestionsRef.current && !suggestionsRef.current.contains(e.target) &&
                inputRef.current && !inputRef.current.contains(e.target)) {
                setShowSuggestions(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const fetchSuggestions = useCallback(async (query) => {
        setSuggestionsLoading(true);
        try {
            const url = query
                ? `/api/routes/tags/search?q=${encodeURIComponent(query)}`
                : '/api/routes/tags/search';
            const data = await apiClient.get(url);
            setSuggestions(data);
        } catch (err) {
            console.error('Tag search error:', err);
        } finally {
            setSuggestionsLoading(false);
        }
    }, []);

    // Check for changes to prevent unnecessary updates
    const hasChanges = React.useMemo(() => {
        if (isMapChanged) return true;

        const initTitle = initialData.title || '';
        const initDesc = initialData.description || '';
        const initStatus = initialData.status || 'PUBLIC';
        const initTags = initialData.tags || [];

        if (title !== initTitle) return true;
        if (description !== initDesc) return true;
        if (status !== initStatus) return true;

        if (tags.length !== initTags.length) return true;
        const sortedTags = [...tags].sort();
        const sortedInitTags = [...initTags].sort();
        return JSON.stringify(sortedTags) !== JSON.stringify(sortedInitTags);
    }, [title, description, status, tags, initialData, isMapChanged]);

    const addTag = (tagName) => {
        const normalized = tagName.trim().toLowerCase();
        if (normalized && !tags.includes(normalized)) {
            setTags([...tags, normalized]);
        }
        setTagInput('');
        setShowSuggestions(false);
        inputRef.current?.focus();
    };

    const handleTagKeyDown = (e) => {
        if (e.nativeEvent.isComposing && e.key === 'Enter') return;

        if (e.key === 'Escape') {
            setShowSuggestions(false);
            return;
        }

        if (e.key === 'Enter') {
            e.preventDefault();
            // If suggestions are showing and there's an exact match, select it
            const exactMatch = suggestions.find(s => s.slug === tagInput.trim().toLowerCase());
            if (exactMatch) {
                addTag(exactMatch.slug);
            } else if (tagInput.trim()) {
                // Allow adding as new tag via Enter only when no suggestions match
                addTag(tagInput.trim());
            }
        }
    };

    const handleTagChange = (e) => {
        const val = e.target.value;
        setTagInput(val);
        setShowSuggestions(true);

        // Debounced search
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            fetchSuggestions(val.trim());
        }, 300);
    };

    const removeTag = (tagToRemove) => {
        setTags(tags.filter(t => t !== tagToRemove));
    };

    // Filter out already-selected tags from suggestions
    const filteredSuggestions = suggestions.filter(s => !tags.includes(s.slug));

    // Check if current input matches any existing suggestion
    const inputMatchesExisting = tagInput.trim() &&
        suggestions.some(s => s.slug === tagInput.trim().toLowerCase());
    const canCreateNew = tagInput.trim() && !inputMatchesExisting;

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/80 backdrop-blur-sm animate-fadeIn" onClick={onClose}></div>

            {/* Modal Content */}
            <div className="relative bg-gray-900 border border-gray-800 rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden animate-slideUp">
                {/* Close Button */}
                <button onClick={onClose} className="absolute top-5 right-5 z-10 text-gray-500 hover:text-white transition-colors bg-gray-800/50 hover:bg-gray-800 p-1.5 rounded-full">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>

                {/* Form Body */}
                <div className="p-6 pt-8 space-y-5 overflow-y-auto max-h-[85vh] custom-scrollbar">
                    {/* Title */}
                    <div className="space-y-2">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Route Title</label>
                        <input
                            type="text"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="Enter a title..."
                            className="w-full bg-gray-800 text-white px-4 py-3 rounded-2xl border border-gray-700 focus:outline-none focus:border-riduck-primary transition-all text-sm font-medium"
                        />
                    </div>

                    {/* Privacy / Status */}
                    <div className="flex items-center justify-between bg-gray-800/30 p-1.5 rounded-xl border border-gray-800">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest pl-3">Visibility</label>
                        <div className="flex bg-gray-900 rounded-lg p-0.5 border border-gray-800">
                            {[
                                { id: 'PUBLIC', label: 'Public', icon: '🌍' },
                                { id: 'LINK_ONLY', label: 'Link Only', icon: '🔗' },
                                { id: 'PRIVATE', label: 'Private', icon: '🔒' }
                            ].map(opt => (
                                <button
                                    key={opt.id}
                                    onClick={() => setStatus(opt.id)}
                                    className={`px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 ${
                                        status === opt.id
                                        ? 'bg-gray-700 text-white shadow-sm'
                                        : 'text-gray-500 hover:text-gray-400 hover:bg-gray-800'
                                    }`}
                                >
                                    <span className="text-[11px]">{opt.icon}</span>
                                    <span className="text-[9px] font-bold uppercase">{opt.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Tags */}
                    <div className="space-y-2 relative">
                        <div className="flex items-center justify-between px-1">
                            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Tags</label>
                            {isAiGenerating && <span className="text-[9px] font-bold text-riduck-primary uppercase animate-pulse flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-riduck-primary animate-ping"></div> AI 분석 중</span>}
                        </div>
                        <div className={`bg-gray-800 rounded-2xl border p-2 min-h-[56px] flex flex-wrap gap-2 transition-all ${isAiGenerating ? 'border-riduck-primary/50 bg-riduck-primary/5' : 'border-gray-700'}`}>
                            {isAiGenerating && tags.length === 0 && (
                                <div className="text-riduck-primary/70 text-xs font-medium flex items-center h-8 px-2 animate-pulse">
                                    최적의 태그를 추출하고 있습니다...
                                </div>
                            )}
                            {tags.map(tag => (
                                <span key={tag} className="bg-riduck-primary/20 text-riduck-primary px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1 border border-riduck-primary/30">
                                    #{tag}
                                    <button onClick={() => removeTag(tag)} className="hover:text-white transition-colors">
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                                        </svg>
                                    </button>
                                </span>
                            ))}
                            <input
                                ref={inputRef}
                                type="text"
                                value={tagInput}
                                onChange={handleTagChange}
                                onKeyDown={handleTagKeyDown}
                                onFocus={() => setShowSuggestions(true)}
                                className="bg-transparent border-none focus:outline-none text-white text-sm flex-1 min-w-[80px] p-1"
                                placeholder={tags.length === 0 ? "Search tags..." : ""}
                            />
                        </div>

                        {/* Suggestions Dropdown */}
                        {showSuggestions && (
                            <div
                                ref={suggestionsRef}
                                className="absolute left-0 right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-2xl overflow-hidden z-10 shadow-xl"
                            >
                                {suggestionsLoading && (
                                    <div className="px-4 py-2 text-gray-500 text-xs">Searching...</div>
                                )}

                                {/* Existing tag suggestions */}
                                {filteredSuggestions.length > 0 && (
                                    <div className="max-h-[180px] overflow-y-auto custom-scrollbar">
                                        {filteredSuggestions.map(s => (
                                            <button
                                                key={s.slug}
                                                onClick={() => addTag(s.slug)}
                                                className="w-full px-4 py-2.5 text-left hover:bg-gray-700/50 transition-colors flex items-center justify-between group"
                                            >
                                                <span className="text-sm text-white font-medium">
                                                    <span className="text-riduck-primary">#</span>{s.name}
                                                </span>
                                                <span className="flex items-center gap-2">
                                                    {s.similarity != null && (
                                                        <span className="text-[10px] text-gray-500">
                                                            {Math.round(s.similarity * 100)}%
                                                        </span>
                                                    )}
                                                    <span className="text-[10px] text-gray-600 bg-gray-700/50 px-1.5 py-0.5 rounded-full">
                                                        {s.count}
                                                    </span>
                                                </span>
                                            </button>
                                        ))}
                                    </div>
                                )}

                                {!suggestionsLoading && filteredSuggestions.length === 0 && tagInput.trim() && (
                                    <div className="px-4 py-2 text-gray-500 text-xs">No matching tags found</div>
                                )}

                                {/* New tag creation — horizontal scroll area */}
                                {canCreateNew && (
                                    <div className="border-t border-gray-700">
                                        <div className="overflow-x-auto whitespace-nowrap px-4 py-2.5" style={{ scrollbarWidth: 'thin' }}>
                                            <span className="text-[10px] text-gray-500 mr-3">Scroll to create new</span>
                                            <span className="inline-block text-gray-600 mr-8">&rarr;</span>
                                            <span className="inline-block" style={{ paddingLeft: '120px' }}>
                                                <button
                                                    onClick={() => addTag(tagInput.trim())}
                                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-700/50 hover:bg-riduck-primary/20 border border-gray-600 hover:border-riduck-primary/50 rounded-full text-xs text-gray-400 hover:text-riduck-primary transition-all"
                                                >
                                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                                                        <path fillRule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clipRule="evenodd" />
                                                    </svg>
                                                    Create &quot;{tagInput.trim()}&quot;
                                                </button>
                                            </span>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Description */}
                    <div className="space-y-2">
                        <div className="flex items-center justify-between px-1">
                            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Description</label>
                            <div className="flex items-center gap-3">
                                {autoTagPayload && description && !isAiGenerating && (() => {
                                    const routeChanged = routeChangedSinceGeneration;
                                    return (
                                        <button
                                            onClick={() => generateAutoTags(autoTagPayload)}
                                            className={`text-[10px] font-bold flex items-center gap-1.5 transition-all ${
                                                routeChanged
                                                    ? 'bg-amber-500/10 border border-amber-500/30 hover:bg-amber-500/20 text-amber-400 px-2.5 py-1 rounded-lg'
                                                    : 'text-riduck-primary hover:brightness-110'
                                            }`}
                                            title="AI가 현재 코스를 다시 분석하여 글을 새로 씁니다."
                                        >
                                            {routeChanged && <span className="text-amber-500/70">루트 변경 감지</span>}
                                            <span>✨ AI로 다시 쓰기</span>
                                        </button>
                                    );
                                })()}
                                <div className="flex bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                                    <button
                                        onClick={() => setDescPreview(false)}
                                        className={`px-2 py-0.5 text-[9px] font-bold uppercase transition-colors ${!descPreview ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-400'}`}
                                    >Edit</button>
                                    <button
                                        onClick={() => setDescPreview(true)}
                                        className={`px-2 py-0.5 text-[9px] font-bold uppercase transition-colors ${descPreview ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-400'}`}
                                    >Preview</button>
                                </div>
                            </div>
                        </div>
                        {descPreview ? (
                            <div
                                className="w-full bg-gray-800 text-white px-4 py-3 rounded-2xl border border-gray-700 text-sm min-h-[200px] max-h-[400px] overflow-y-auto custom-scrollbar prose prose-invert prose-sm prose-p:my-1 prose-headings:my-1 cursor-text"
                                onClick={() => {
                                    // Only switch to edit if it was a simple click, not a text selection drag
                                    if (!window.getSelection()?.toString()) {
                                        setDescPreview(false);
                                    }
                                }}
                            >
                                {description ? <ReactMarkdown>{description}</ReactMarkdown> : <span className="text-gray-500">Nothing to preview</span>}
                            </div>
                        ) : (
                            <div className="relative">
                                <textarea
                                    rows={12}
                                    value={description}
                                    onChange={(e) => setDescription(e.target.value)}
                                    disabled={isAiGenerating}
                                    placeholder={isAiGenerating ? "" : "Tell more about this course..."}
                                    className={`w-full bg-gray-800 text-white px-4 py-4 rounded-2xl border focus:outline-none focus:border-riduck-primary transition-all text-sm font-medium resize-none leading-relaxed ${
                                        isAiGenerating 
                                        ? 'border-riduck-primary/50 bg-riduck-primary/5 text-riduck-primary/80 animate-pulse' 
                                        : 'border-gray-700'
                                    }`}
                                />
                                {isAiGenerating && !description && (
                                    <div className="absolute top-4 left-4 text-sm text-riduck-primary/70 font-medium animate-pulse flex items-start gap-2.5">
                                        <div className="w-4 h-4 mt-0.5 border-2 border-riduck-primary/50 border-t-riduck-primary rounded-full animate-spin shrink-0"></div>
                                        <span>AI가 코스 데이터를 분석하여 최적의 설명을 작성하고 있습니다... ✍️</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                </div>

                {/* Footer Actions */}
                <div className="p-6 border-t border-gray-800 bg-gray-900/50 backdrop-blur-md grid grid-cols-2 gap-3">
                    {/* Overwrite / Update Button */}
                    <button
                        onClick={() => onSave({ title, description, status, tags, isOverwrite: true })}
                        disabled={isLoading || isAiGenerating || !isOwner || !initialData.id || !title.trim() || !hasChanges}
                        className={`py-4 rounded-2xl font-bold text-sm transition-all border flex items-center justify-center ${
                            !isOwner || !initialData.id || !hasChanges || isAiGenerating
                            ? 'bg-gray-800/30 text-gray-600 border-gray-800 cursor-not-allowed opacity-70'
                            : 'bg-gray-800 hover:bg-gray-700 text-white border-gray-700'
                        }`}
                        title={
                            isAiGenerating ? "AI is generating description..." :
                            (!isOwner ? "You can only update your own routes" :
                            (!initialData.id ? "Save as new first" :
                            (!hasChanges ? "No changes to update" : "Overwrite existing route")))
                        }
                    >
                        {hasChanges ? "Update Existing" : "No Changes"}
                    </button>

                    {/* Save as New / Fork Button */}
                    <button
                        onClick={() => onSave({ title, description, status, tags, isOverwrite: false })}
                        disabled={isLoading || isAiGenerating || !title.trim()}
                        className={`py-4 rounded-2xl font-black text-sm shadow-lg transition-all flex items-center justify-center gap-2 ${
                            isAiGenerating || isLoading
                            ? 'bg-gray-800 border border-gray-700 text-gray-400 cursor-not-allowed'
                            : 'bg-riduck-primary hover:brightness-110 text-white shadow-riduck-primary/20 disabled:opacity-50'
                        }`}
                    >
                        {isAiGenerating ? (
                            <>
                                <div className="animate-spin h-4 w-4 border-2 border-gray-500 rounded-full border-t-gray-400"></div>
                                <span>AI 분석 대기중...</span>
                            </>
                        ) : isLoading ? (
                            <>
                                <div className="animate-spin h-5 w-5 border-2 border-white rounded-full border-t-transparent"></div>
                                <span>Saving...</span>
                            </>
                        ) : (
                            initialData.id ? 'Fork as New' : 'Save to Cloud'
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default SaveRouteModal;
